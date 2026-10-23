#include <Arduino.h>

// ======================== 底盘电调输出引脚 ========================
#define THROTTLE_PIN 21  // 接电调 Throttle 通道（油门）
#define STEER_PIN    47  // 接电调 Steering 通道（转向）

// ======================== 云台舵机输出引脚 ========================
#define GIMBAL_PITCH_PIN 48  // 云台俯仰
#define GIMBAL_YAW_PIN   45  // 云台旋转

// ======================== PWM 参数 ========================
#define PWM_FREQ         50
#define PWM_RESOLUTION   13
#define PWM_MAX          8191 

// ======================== RC 接收器引脚 ========================
#define NUM_CHANNELS 10
const uint8_t RC_PINS[NUM_CHANNELS] = {1, 2, 42, 41, 40, 39, 38, 37, 36, 35};

// ======================== RC 通道映射 ========================
#define RC_CH_STEER    0  // CH1: 转向
#define RC_CH_THROTTLE 1  // CH2: 油门
#define RC_CH_PITCH    2  // CH3: 云台俯仰
#define RC_CH_YAW      3  // CH4: 云台旋转
#define RC_CH_SAVE     4  // CH5: 保存触发器

// ======================== 全局变量 ========================
// RC 相关
volatile uint32_t pulseWidths[NUM_CHANNELS];
volatile uint32_t lastRisingEdge[NUM_CHANNELS];
unsigned long lastRCUpdateTime = 0;
const unsigned long RC_TIMEOUT_MS = 200;  // RC 信号超时时间

// 串口上位机相关
unsigned long lastSerialCommandTime = 0;
const unsigned long SERIAL_TIMEOUT_MS = 500;  // 串口超时时间
bool serialStopped = true;

// 云台当前脉冲宽度（用于记录和发送）
int currentGimbalPitchPulse = 1500;  // 默认中位
int currentGimbalYawPulse = 1500;    // 默认中位

// 控制模式
enum ControlMode {
  MODE_RC,      // 遥控器控制
  MODE_SERIAL,  // 串口上位机控制
  MODE_IDLE     // 空闲（无信号）
};
ControlMode currentMode = MODE_IDLE;

// ======================== 按钮防抖和边沿检测相关 ========================
bool lastSaveButtonState = false;  // 上一次保存按钮状态
unsigned long lastSaveDebounceTime = 0;  // 最后一次保存时间（防重复）
const unsigned long SAVE_DEBOUNCE_MS = 500;  // 500ms 防重复间隔

// ======================== RC 中断处理 ========================
void IRAM_ATTR gpio_isr_handler(void* arg) {
  uint32_t channel = (uint32_t)arg;
  uint8_t pin = RC_PINS[channel];
  uint32_t now = micros();
  
  if (digitalRead(pin) == HIGH) {
    lastRisingEdge[channel] = now;
  } else {
    if (lastRisingEdge[channel] != 0) {
      uint32_t width = now - lastRisingEdge[channel];
      if (width > 500 && width < 2500) {
        pulseWidths[channel] = width;
      }
    }
  }
}

// ======================== RC 初始化 ========================
void setupRC() {
  for (int i = 0; i < NUM_CHANNELS; i++) {
    pinMode(RC_PINS[i], INPUT_PULLUP);
    gpio_set_intr_type((gpio_num_t)RC_PINS[i], GPIO_INTR_ANYEDGE);
    gpio_install_isr_service(0);
    gpio_isr_handler_add((gpio_num_t)RC_PINS[i], gpio_isr_handler, (void*)i);
    pulseWidths[i] = 0;
    lastRisingEdge[i] = 0;
  }
}

// ======================== 速度转换函数 ========================
int speedToMicroseconds(int val) {
  val = constrain(val, -30, 30);
  
  if (val > 0) {
    return map(val, 1, 30, 1600, 2000);  // 正向
  } else if (val < 0) {
    return map(val, -30, -1, 1000, 1400);  // 反向
  } else {
    return 1500;  // 中位停止
  }
}

// ======================== RC 脉冲宽度转速度值 ========================
// 将 RC 脉冲宽度 (1000-2000us) 转换为速度值 (-30 到 30)
int pulseWidthToSpeed(uint32_t pulseWidth) {
  if (pulseWidth < 1000 || pulseWidth > 2000) {
    return 0;  // 无效信号
  }
  
  // 1500 为中位，范围 ±500us 映射到 ±30
  int neutral = 1500;
  int deadzone = 50;  // 死区，避免抖动
  
  if (abs((int)pulseWidth - neutral) < deadzone) {
    return 0;
  }
  
  if (pulseWidth > neutral) {
    return map(pulseWidth, neutral + deadzone, 2000, 1, 30);
  } else {
    return map(pulseWidth, 1000, neutral - deadzone, -30, -1);
  }
}

// ======================== PWM 输出辅助函数 ========================
void setPinMicroseconds(int pin, int us) {
  uint32_t duty = (us * PWM_MAX) / 20000;
  ledcWrite(pin, duty);
}

// ======================== 设置底盘信号 ========================
void setChassisSignal(int throttle, int steer) {
  int t_us = speedToMicroseconds(throttle);
  int s_us = speedToMicroseconds(-steer);

  setPinMicroseconds(THROTTLE_PIN, t_us);
  setPinMicroseconds(STEER_PIN, s_us);
}

// ======================== 设置云台信号 ========================
void setGimbalSignal(int pitch, int yaw) {
  int p_us = speedToMicroseconds(pitch);
  int y_us = speedToMicroseconds(yaw);

  setPinMicroseconds(GIMBAL_PITCH_PIN, p_us);
  setPinMicroseconds(GIMBAL_YAW_PIN, y_us);
  
  // 保存当前云台脉冲宽度，用于数据记录
  currentGimbalPitchPulse = p_us;
  currentGimbalYawPulse = y_us;
}

// ======================== 检查 RC 信号有效性 ========================
bool isRCActive() {
  // 检查主要控制通道（转向和油门）是否有有效信号
  bool steerValid = (pulseWidths[RC_CH_STEER] > 500 && pulseWidths[RC_CH_STEER] < 2500);
  bool throttleValid = (pulseWidths[RC_CH_THROTTLE] > 500 && pulseWidths[RC_CH_THROTTLE] < 2500);
  
  return steerValid && throttleValid;
}

// ======================== 处理 RC 控制 ========================
void handleRCControl() {
  if (isRCActive()) {
    // 读取底盘控制通道
    int throttle = pulseWidthToSpeed(pulseWidths[RC_CH_THROTTLE]);  // CH2: 油门
    int steer = pulseWidthToSpeed(pulseWidths[RC_CH_STEER]);        // CH1: 转向
    
    // 读取云台控制通道
    int pitch = pulseWidthToSpeed(pulseWidths[RC_CH_PITCH]);        // CH3: 俯仰
    int yaw = pulseWidthToSpeed(pulseWidths[RC_CH_YAW]);            // CH4: 旋转
    
    // 检查保存按钮（CH5）- 边沿检测
    bool currentSaveButtonState = (pulseWidths[RC_CH_SAVE] > 1500);  // 高电平表示按下
    
    // 检测上升沿（从松开变为按下）
    bool saveButtonPressed = false;
    if (currentSaveButtonState && !lastSaveButtonState) {
      // 检查防重复时间间隔
      if (millis() - lastSaveDebounceTime >= SAVE_DEBOUNCE_MS) {
        saveButtonPressed = true;
        lastSaveDebounceTime = millis();
      }
    }
    
    // 更新上次状态
    lastSaveButtonState = currentSaveButtonState;
    
    // 输出控制信号
    setChassisSignal(throttle, steer);
    setGimbalSignal(pitch, yaw);
    
    // 如果检测到保存按钮按下（上升沿），发送当前云台姿态
    if (saveButtonPressed) {
      Serial.printf("SAVE_PULSE:%d,%d\r\n", currentGimbalPitchPulse, currentGimbalYawPulse);
      Serial.printf("INFO: Pose saved at %lu ms\r\n", millis());
    }
    
    lastRCUpdateTime = millis();
    
    if (currentMode != MODE_RC) {
      currentMode = MODE_RC;
      Serial.println("Mode: RC Control\r\n");
    }
  } else if (millis() - lastRCUpdateTime > RC_TIMEOUT_MS) {
    // RC 信号丢失
    if (currentMode == MODE_RC) {
      setChassisSignal(0, 0);
      setGimbalSignal(0, 0);
      currentMode = MODE_IDLE;
      Serial.println("RC Signal Lost\r\n");
    }
  }
}

// ======================== 处理串口控制 ========================
void handleSerialControl() {
  // 只有在非 RC 模式下才处理串口指令
  if (currentMode == MODE_RC) {
    return;  // RC 优先级高于串口
  }
  
  if (Serial.available() > 0) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    
    // 解析格式: throttle,steer,pitch,yaw,checksum
    int commaPositions[4];
    int commaCount = 0;
    
    for (int i = 0; i < line.length() && commaCount < 4; i++) {
      if (line.charAt(i) == ',') {
        commaPositions[commaCount++] = i;
      }
    }
    
    if (commaCount == 4) {
      int throttle = line.substring(0, commaPositions[0]).toInt();
      int steer = line.substring(commaPositions[0] + 1, commaPositions[1]).toInt();
      int pitch = line.substring(commaPositions[1] + 1, commaPositions[2]).toInt();
      int yaw = line.substring(commaPositions[2] + 1, commaPositions[3]).toInt();
      int chk = line.substring(commaPositions[3] + 1).toInt();
      
      // 校验和验证
      if (throttle + steer + pitch + yaw == chk) {
        setChassisSignal(throttle, steer);
        setGimbalSignal(pitch, yaw);
        
        lastSerialCommandTime = millis();
        serialStopped = false;
        
        if (currentMode != MODE_SERIAL) {
          currentMode = MODE_SERIAL;
          Serial.println("Mode: Serial Control\r\n");
        }
        
        Serial.printf("Serial T:%d S:%d P:%d Y:%d\r\n", throttle, steer, pitch, yaw);
      } else {
        Serial.println("Checksum Error\r\n");
      }
    }
  }
  
  // 串口超时停止
  if (!serialStopped && (millis() - lastSerialCommandTime > SERIAL_TIMEOUT_MS)) {
    setChassisSignal(0, 0);
    setGimbalSignal(0, 0);
    serialStopped = true;
    currentMode = MODE_IDLE;
    Serial.println("Serial Timeout: Safety Stop\r\n");
  }
}

// ======================== 初始化 ========================
void setup() {
  Serial.begin(115200);
  
  // 初始化底盘 PWM 输出
  ledcAttach(THROTTLE_PIN, PWM_FREQ, PWM_RESOLUTION);
  ledcAttach(STEER_PIN, PWM_FREQ, PWM_RESOLUTION);
  
  // 初始化云台 PWM 输出
  ledcAttach(GIMBAL_PITCH_PIN, PWM_FREQ, PWM_RESOLUTION);
  ledcAttach(GIMBAL_YAW_PIN, PWM_FREQ, PWM_RESOLUTION);
  
  // 初始化 RC 输入
  setupRC();
  
  // 设置初始中位
  setChassisSignal(0, 0);
  setGimbalSignal(0, 0);
  
  Serial.println("=== Fire Inspection Robot Control System ===");
  Serial.println("RC Mapping: CH1=Steer, CH2=Throttle, CH3=Pitch, CH4=Yaw");
  Serial.println("Serial Format: throttle,steer,pitch,yaw,checksum");
  Serial.println("Priority: RC > Serial");
  Serial.println("Save Button: Edge-triggered (only on press)");
  Serial.println("System Ready\r\n");
}

// ======================== 发送姿态脉冲 ========================
void sendGimbalPulses() {
  static unsigned long lastSendTime = 0;
  const unsigned long SEND_INTERVAL_MS = 100;  // 每 100ms 发送一次
  
  if (millis() - lastSendTime >= SEND_INTERVAL_MS) {
    // 发送当前云台脉冲宽度给上位机
    Serial.printf("GIMBAL_PULSE:%d,%d\r\n", currentGimbalPitchPulse, currentGimbalYawPulse);
    lastSendTime = millis();
  }
}

// ======================== 主循环 ========================
void loop() {
  // 优先处理 RC 控制（会自动切换模式）
  handleRCControl();
  
  // 处理串口控制（只有在非 RC 模式下才会执行）
  handleSerialControl();
  
  // 定期发送云台姿态脉冲
  sendGimbalPulses();
  
  delay(10);  // 减少 CPU 占用
}