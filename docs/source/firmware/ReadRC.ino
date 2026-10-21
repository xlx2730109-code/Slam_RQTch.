#include <Arduino.h>
#include <driver/pcnt.h>
#define NUM_CHANNELS 10
const uint8_t RC_PINS[NUM_CHANNELS] = {1, 2, 42, 41, 40, 39, 38, 37, 36, 35};
pcnt_unit_t pcnt_units[NUM_CHANNELS];
volatile uint32_t pulseWidths[NUM_CHANNELS];
volatile uint32_t lastRisingEdge[NUM_CHANNELS];
void IRAM_ATTR gpio_isr_handler(void* arg)
{
  uint32_t channel = (uint32_t)arg;
  uint8_t pin = RC_PINS[channel];
  uint32_t now = micros();
  if (digitalRead(pin) == HIGH)
  {
    lastRisingEdge[channel] = now;
  }
  else
  {
    if (lastRisingEdge[channel] != 0)
    {
      uint32_t width = now - lastRisingEdge[channel];
      if (width > 500 && width < 2500)
      {
        pulseWidths[channel] = width;
      }
    }
  }
}

void setupPCNT()
{
  pcnt_config_t pcnt_config =
  {
    .pulse_gpio_num = -1,  // 不使用脉冲输入
    .ctrl_gpio_num = -1,   // 不使用控制输入
    .lctrl_mode = PCNT_MODE_KEEP,
    .hctrl_mode = PCNT_MODE_KEEP,
    .pos_mode = PCNT_COUNT_DIS,
    .neg_mode = PCNT_COUNT_DIS,
    .counter_h_lim = 0,
    .counter_l_lim = 0,
    .unit = PCNT_UNIT_0,
    .channel = PCNT_CHANNEL_0,
  };
  for (int i = 0; i < NUM_CHANNELS; i++)
  {
    // 初始化GPIO中断
    pinMode(RC_PINS[i], INPUT_PULLUP);
    gpio_set_intr_type((gpio_num_t)RC_PINS[i], GPIO_INTR_ANYEDGE);
    gpio_install_isr_service(0);
    gpio_isr_handler_add((gpio_num_t)RC_PINS[i], gpio_isr_handler, (void*)i);
    pulseWidths[i] = 0;
    lastRisingEdge[i] = 0;
  }
}

void setup()
{
  Serial.begin(115200);
  setupPCNT();
}

void loop()
{
  uint32_t now = micros();
  for (int i = 0; i < NUM_CHANNELS; i++)
  {
    if (now - lastRisingEdge[i] > 10000) pulseWidths[i] = 1500;
  }

  for (int i = 0; i < NUM_CHANNELS; i++)
  {
    Serial.print(pulseWidths[i]);
    Serial.print('\t');
  }
  Serial.println();


}
