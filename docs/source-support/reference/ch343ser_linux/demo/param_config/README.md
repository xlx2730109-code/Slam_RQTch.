# **1. 概述**

CH34xSerCfg配置软件用于WCH USB转串口系列芯片进行USB参数配置，通过该工具可对芯片的厂商识别码VID、产品识别码PID、最大电流值、厂商信息和产品信息字符串描述符等参数进行修改配置。
程序支持配置型号: CH343P CH342F CH344Q/L CH346C CH347T/F CH348Q/L CH9101U/H/R/Y CH9102F CH9103M CH9104L CH9105W CH9111L CH9114L/W/F CH9344Q CH339W等。
(注：CH342F/CH9102F批号倒数第4位是字母的芯片，则内置EEPROM可支持此配置功能。)

## **1.1 CH34xSerCfg 功能说明**

本节对 CH34xSerCfg 软件功能进行说明，使用前需安装对应产品VCP驱动，下载链接: 

https://github.com/WCHSoftGroup/ch9344ser_linux（配置CH348Q/L和CH9344Q时使用）

https://github.com/WCHSoftGroup/ch343ser_linux（配置其他型号时使用）

### 1.1.1 填写配置项

在CONFIG.INI文件中填写需要修改的配置项，**不需要修改的配置项可不用填写**。

| **配置项**                      | **说明**                           | **可选值/注意事项**                                          |
| ------------------------------- | :--------------------------------- | :----------------------------------------------------------- |
| **VendorID**                    | 厂商识别码 (VID)                     | 需使用合法ID (修改ID后，原VCP驱动程序将无法适用该芯片)      |
| **ProductID**                   | 产品识别码 (PID)                     | 需使用合法ID (修改ID后，原VCP驱动程序将无法适用该芯片)                        |
| **Serial_String_Enable**       | 开启USB设备序列号字符串使能          | `y`: 开启，`n`: 关闭                                         |
| **Product_String_Enable**      | 开启USB产品信息字符串使能            | `y`: 开启，`n`: 关闭                                         |
| **Manufacturer_String_Enable** | 开启USB厂商信息字符串使能            | `y`: 开启，`n`: 关闭                                         |
| **Serial_String**         | USB设备序列号字符串                  | 字符长度≤10. 示例值: `abcdef`                           |
| **Product_String** | USB产品信息字符串                    | 字符长度≤18. 示例值: `USB_to_Serial`                   |
| **Manufacturer_String** | USB厂商信息字符串                    | 字符长度≤18. 示例值: `www.wch.cn`                       |
| **MaxPower(mA)**             | 最大电源电流值                       | 单位为毫安(mA)，示例值为`300`                                |
| **PowerMode**        | USB供电方式                          | `Self-Powered` 或 `Bus-Powered`                              |
| **Remote_Wakeup_Enable**      | 远程唤醒(睡眠唤醒)功能             | `y`: 开启，`n`: 关闭                                         |
| **PIN_USE_EEPROM_Enable**     | 芯片引脚是否使用EEPROM的默认配置     | `y`: 开启，`n`: 关闭 (支持CH9102F和CH9101U/H/R/Y)        |
| **CDC_CTSRTS_FlowControl_Enable** | CDC模式下是否启用硬件流控 (CTS/RTS) | `y`: 开启，`n`: 关闭                                         |
| **TurnOff_SuspendMode_Enable**| 芯片USB睡眠功能                      | `y`: 开启，`n`: 关闭 (支持CH348Q/L CH344Q CH9114L/W/F CH9111) |
| **DTR_MUX_TNOW_SoftSet_Enable**| TNOW/DTR引脚功能软件配置使能         | `y`: 开启，`n`: 关闭 (支持CH344 CH348 CH9114)          |
| **UARTx_TNOW_DTR_SETBITS**    | UARTx TNOW/DTR引脚功能具体配置       | `bit0~bit7`对应`UART0~UART7`，`1`: TNOW `0`: DTR，(支持CH344 CH348 CH9114，需先设置`DTR_MUX_TNOW_SoftSet_Enable=y`，填入8位16进制数值) |
| **CH9105_GPIO_Enable**        | CH9105W芯片GPIO配置使能              | `y`: 开启，`n`: 关闭                                         |
| **CH9105_GPIO_Enable_BITS**   | CH9105W芯片GPIO引脚具体配置           | 填入16位16进制数值(如 `0xFFFF`)，配合`CH9105_GPIO_Enable=y`使用 |
| **CH9101RY_MODEM_Enable**      | CH9101R/Y芯片MODEM引脚功能使能       | `y`: 开启，`n`: 关闭                        |
| **CH9101RY_TXS_MUX_DSR_Enable**| CH9101R/Y芯片 TXS 与 DSR# 引脚复用使能 | `y`: DSR#功能，`n`: TXS功能(默认)           |
| **CH9101RY_RXS_MUX_RI_Enable** | CH9101R/Y芯片 RXS 与 RI# 引脚复用使能  | `y`: RI#功能，`n`: RXS功能(默认)            |
| **CH9101RY_TNOW_MUX_DCD_Enable**| CH9101R/Y芯片 TNOW 与 DCD# 引脚复用使能 | `y`: DCD#功能，`n`: TNOW功能(默认)          |
| **CH9101RY_SLEEP_MUX_DTR_Enable**| CH9101R/Y芯片 SLEEP 与 DTR# 引脚复用使能 | `y`: DTR#功能，`n`: SLEEP功能(默认)         |
| **CH346_Config_Enable**        | CH346扩展配置使能                    | `y`: 开启，`n`: 关闭                                         |
| **CH346_Config_Freq**           | CH346芯片工作主频                    | 填主频数值(十进制)，例如 `120000000`                         |
| **CH346_Config_Mode**           | CH346芯片工作模式                    | 有效值为`0`/`1`/`2`，分别表示工作模式0/1/2                   |
| **CH346_Config_PLen**           | CH346通信包大小                      | 被动并口或被动SPI接口通信包大小，必须是512的倍数，默认为512字节 |
| **CH346_Config_M0_IO0**         | CH346工作模式0的IO0(PIN12)功能配置   | `0x00`: RXD0功能，`0x01`: TX_S功能，`0x02`: ACT功能，`0x03`: GPIO6功能 |
| **CH346_Config_M0_IO1**         | CH346工作模式0的IO1(PIN13)功能配置   | `0x00`: TXD0功能，`0x01`: RX_S功能，`0x02`: SUSP功能，`0x03`: GPIO7功能 |
| **CH346_Config_M1_IO0**         | CH346工作模式1的IO0(PIN15)功能配置   | `0x00`: DCD0功能，`0x01`: TX_S功能，`0x02`: 无效，`0x03`: GPIO4功能 |
| **CH346_Config_M1_IO1**         | CH346工作模式1的IO1(PIN16)功能配置   | `0x00`: DTR0功能，`0x01`: RX_S功能，`0x02`: 无效，`0x03`: GPIO2功能 |
| **CH346_Config_M2_IO0**         | CH346工作模式2的IO0(PIN13)功能配置   | `0x00`: DCD1功能，`0x01`: SUSP功能，`0x02`: 无效，`0x03`: GPIO7功能 |
| **CH346_Config_M2_IO1**         | CH346工作模式2的IO1(PIN15)功能配置   | `0x00`: DCD0功能，`0x01`: TX_S功能，`0x02`: 无效，`0x03`: GPIO4功能 |
| **CH346_Config_M2_IO2**         | CH346工作模式2的IO2(PIN16)功能配置   | `0x00`: DTR0功能，`0x01`: RX_S功能，`0x02`: 无效，`0x03`: GPIO2功能 |
| **CH346_Config_M2_IO3**         | CH346工作模式2的IO3(PIN17)功能配置   | `0x00`: DSR0功能，`0x01`: ACT功能，`0x02`: 无效，`0x03`: GPIO3功能 |

**注意事项**: 

- 修改设备的 VID 或 PID 后，原 VCP 驱动将不再适用于该硬件，设备此时只能使用系统自带 CDC 驱动(CH340/CH348 系列不支持系统 CDC 驱动)。若需要使用 VCP 驱动，需在驱动static const struct usb_device_id xxx_ids[] 结构体数组中，增加对应的ID匹配项，重新编译加载驱动。
- 如果需要通过不同的标识信息来区别多芯片，建议通过修改Serial_String/Product_String/Manufacturer_String字符串信息来区分.
- **不要修改CONFIG.INI文件中除配置项外的其他内容或格式.**

### 1.1.2 编译和执行示例

- 从`ch343ser_linux`的`lib`文件夹中获取`libch34xcfg.so(.a)`库文件，将库文件放置到系统标准库路径下或者param_config目录
- 进入param_config目录下，执行命令: `gcc ch34x_demo_param_config.c -lch34xcfg -o CH34xSerCfg`
- 命令格式: `./CH34xSerCfg -d [串口设备路径] -c [配置文件路径]`
输入g: 获取当前配置
输入s: 配置芯片的EEPROM
输入d: 向EEPROM写入厂商默认配置
输入q: 退出程序

### 1.1.3 使用示例

执行程序

```shell
./CH34xSerCfg -d /dev/ttyCH343USB0 -c CONFIG.INI
```

配置文件

```shell
VendorID=
ProductID=

Serial_String_Enable=y
Product_String_Enable=y
Manufacturer_String_Enable=y
Serial_String=abcdef
Product_String=USB_xxx_Serial
Manufacturer_String=www.wch.cn

MaxPower(mA)=300
PowerMode=Bus-Powered
Remote_Wakeup_Enable=no

PIN_USE_EEPROM_Enable=no
CDC_CTSRTS_FlowControl_Enable=no
TurnOff_SuspendMode_Enable=no

# CH344/CH348/CH9114
DTR_MUX_TNOW_SoftSet_Enable=y
UARTx_TNOW_DTR_SETBITS=00
# CH9101RY
CH9101RY_MODEM_Enable=y
CH9101RY_TXS_MUX_DSR_Enable=y
CH9101RY_RXS_MUX_RI_Enable=y
CH9101RY_TNOW_MUX_DCD_Enable=y
CH9101RY_SLEEP_MUX_DTR_Enable=y
# CH346
CH346_Config_Enable=n
CH346_Config_Freq=
CH346_Config_Mode=
CH346_Config_PLen=
CH346_Config_M0_IO0=
CH346_Config_M0_IO1=
CH346_Config_M1_IO0=
CH346_Config_M1_IO1=
CH346_Config_M2_IO0=
CH346_Config_M2_IO1=
CH346_Config_M2_IO2=
CH346_Config_M2_IO3=
```

查看当前eeprom配置(**在ch34x_cfg_lib.h文件中添加\#define DEBUG宏定义，可打印显示eeprom数据内容; 或调用ch34x_cfg_get函数获取**)
```shell
sudo ./CH34xSerCfg -d /dev/ttyCH9344USB0 -c CONFIG.INI 
Chip type:CH348Q

press g to get usb config， s to set usb config， d to set default config， q to quit this app.
g
current eeprom buffer:
          00 01 02 03 04 05 06 07  08 09 0A 0B 0C 0D 0E 0F 
00000000: 53 23 60 00 86 1A D9 55  00 00 32 80 00 00 00 00  |S#`....U..2.....|
00000010: 16 16 03 45 00 33 00 33  00 39 00 33 00 39 00 45  |...E.3.3.9.3.9.E|
00000020: 00 33 00 33 00 39 00 00  20 20 03 55 00 53 00 42  |.3.3.9..  .U.S.B|
00000030: 00 32 00 2E 00 30 00 20  00 54 00 6F 00 20 00 4D  |.2...0. .T.o. .M|
00000040: 00 75 00 6C 00 74 00 69  00 00 00 00 00 00 00 00  |.u.l.t.i........|
00000050: 0E 0E 03 77 00 63 00 68  00 2E 00 63 00 6E 00 00  |...w.c.h...c.n..|
00000060: 00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00  |................|
00000070: 00 00 00 00 00 00 00 00  00                       |.........|

USB Configuration:
	VendorId: 0x1A86
	ProductId: 0x55D9
	Max power: 100mA
	Power mode: Bus-Powered
	Remote wakeup: Disabled
	Serial string: Disabled []
	Product string: Enabled [USB2.0 To Multi]
	Manufacturer string: Enabled [wch.cn]
```

配置示例: 
```shell
press g to get usb config， s to set usb config， d to set default config， q to quit this app.
s
Setting USB configuration from file:CONFIG.INI...
current eeprom buffer:
          00 01 02 03 04 05 06 07  08 09 0A 0B 0C 0D 0E 0F 
00000000: 53 23 60 00 86 1A D9 55  00 00 32 80 00 00 00 00  |S#`....U..2.....|
00000010: 16 16 03 45 00 33 00 33  00 39 00 33 00 39 00 45  |...E.3.3.9.3.9.E|
00000020: 00 33 00 33 00 39 00 00  20 20 03 55 00 53 00 42  |.3.3.9..  .U.S.B|
00000030: 00 32 00 2E 00 30 00 20  00 54 00 6F 00 20 00 4D  |.2...0. .T.o. .M|
00000040: 00 75 00 6C 00 74 00 69  00 00 00 00 00 00 00 00  |.u.l.t.i........|
00000050: 0E 0E 03 77 00 63 00 68  00 2E 00 63 00 6E 00 00  |...w.c.h...c.n..|
00000060: 00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00  |................|
00000070: 00 00 00 00 00 00 00 00  00                       |.........|
new eeprom buffer:
          00 01 02 03 04 05 06 07  08 09 0A 0B 0C 0D 0E 0F 
00000000: 53 23 E0 00 86 1A D9 55  00 00 32 80 00 00 00 00  |S#.....U..2.....|
00000010: 16 16 03 77 00 77 00 77  00 2E 00 77 00 63 00 68  |...w.w.w...w.c.h|
00000020: 00 2E 00 63 00 6E 00 00  16 16 03 77 00 77 00 77  |...c.n.....w.w.w|
00000030: 00 2E 00 77 00 63 00 68  00 2E 00 63 00 6E 00 00  |...w.c.h...c.n..|
00000040: 00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00  |................|
00000050: 16 16 03 77 00 77 00 77  00 2E 00 77 00 63 00 68  |...w.w.w...w.c.h|
00000060: 00 2E 00 63 00 6E 00 00  00 00 00 00 00 00 00 00  |...c.n..........|
00000070: 00 00 00 00 00 00 00 00  00                       |.........|
USB configuration set successfully from file:CONFIG.INI
```

向EEPROM写入厂商默认配置
```shell
press g to get usb config， s to set usb config， d to set default config， q to quit this app.
d
Setting default USB configuration...
bcdDevice:00 00
new eeprom buffer:
          00 01 02 03 04 05 06 07  08 09 0A 0B 0C 0D 0E 0F 
00000000: 53 23 60 00 86 1A D9 55  00 00 32 80 00 00 00 00  |S#`....U..2.....|
00000010: 00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00  |................|
00000020: 00 00 00 00 00 00 00 00  20 20 03 55 00 53 00 42  |........  .U.S.B|
00000030: 00 32 00 2E 00 30 00 20  00 54 00 6F 00 20 00 4D  |.2...0. .T.o. .M|
00000040: 00 75 00 6C 00 74 00 69  00 00 00 00 00 00 00 00  |.u.l.t.i........|
00000050: 0E 0E 03 77 00 63 00 68  00 2E 00 63 00 6E 00 00  |...w.c.h...c.n..|
00000060: 00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00  |................|
00000070: 00 00 00 00 00 00 00 00  00                       |.........|
Default USB configuration set successfully.
```

配置完成后，芯片需复位或重新上电，然后可在对应的USB设备目录查看配置信息

```shell
book@100ask:/sys/bus/usb/devices/3-2$ ls
3-2:1.0  3-2:1.5            bcdDevice            bmAttributes        busnum         devpath    ltm_capable   product    speed      version
3-2:1.1  3-2:1.6            bConfigurationValue  bMaxPacketSize0     configuration  driver     manufacturer  quirks     subsystem
3-2:1.2  3-2:1.7            bDeviceClass         bMaxPower           descriptors    ep_00      maxchild      removable  tx_lanes
3-2:1.3  authorized         bDeviceProtocol      bNumConfigurations  dev            idProduct  port          remove     uevent
3-2:1.4  avoid_reset_quirk  bDeviceSubClass      bNumInterfaces      devnum         idVendor   power         rx_lanes   urbnum
book@100ask:/sys/bus/usb/devices/3-2$
book@100ask:/sys/bus/usb/devices/3-2$
book@100ask:/sys/bus/usb/devices/3-2$ cat manufacturer
wch.cn
book@100ask:/sys/bus/usb/devices/3-2$ cat idProduct
55e8
book@100ask:/sys/bus/usb/devices/3-2$ cat product
USB Quad_Serial

```

