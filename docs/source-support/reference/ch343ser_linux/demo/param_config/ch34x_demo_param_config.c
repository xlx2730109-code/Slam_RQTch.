/*
 * CH343/CH342/CH344/CH347/CH348/CH9344/CH9101/CH9102/CH9103/CH9104/CH9111/CH9114/CH346
 * parameter configuration application
 * Copyright (C) 2026 Nanjing Qinheng Microelectronics Co., Ltd.
 * Web: http://wch.cn
 * Author: WCH <tech@wch.cn>
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License.
 *
 * Cross-compile with cross-gcc -I /path/to/cross-kernel/include
 *
 * V1.0 - initial version
 */

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>
#include <getopt.h>
#include <fcntl.h>
#include <errno.h>
#include <string.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <assert.h>
#include <ctype.h>
#include <stdbool.h>

#include "ch343_lib.h"
#include "ch9344_lib.h"
#include "ch34x_cfg_lib.h"

static void print_usb_config(const usbConfig_t *cfg)
{
    printf("\nUSB Configuration:\n");
    printf("\tVendorId: 0x%04X\n", cfg->vendor_id);
    printf("\tProductId: 0x%04X\n", cfg->product_id);

    printf("\tMax power: %dmA\n", cfg->max_power);
    printf("\tPower mode: %s\n", cfg->power_mode);
    printf("\tRemote wakeup: %s\n", cfg->remote_wakeup ? "Enabled" : "Disabled");

    printf("\tSerial string: %s [%s]\n", cfg->serial_string_enable ? "Enabled" : "Disabled",
           cfg->serial_string_enable ? cfg->serial_string : "");
    printf("\tProduct string: %s [%s]\n", cfg->product_string_enable ? "Enabled" : "Disabled",
           cfg->product_string_enable ? cfg->product_string : "");
    printf("\tManufacturer string: %s [%s]\n", cfg->manufacturer_string_enable ? "Enabled" : "Disabled",
           cfg->manufacturer_string_enable ? cfg->manufacturer_string : "");
}

int main(int argc, char *argv[])
{
    int ret, i;
    int opt;
    char choice;
    char device_path[64] = {0};
    char cfgfile_path[64] = {0};
    uint8_t eepBuf[0x82 + 1] = {0};
    CH34xCfg_t *pcfg = NULL;
    usbConfig_t usbCfg;

    while ((opt = getopt(argc, argv, "d:c:")) != -1) {
        switch (opt) {
        case 'd':
            strncpy(device_path, optarg, sizeof(device_path) - 1);
            break;
        case 'c':
            strncpy(cfgfile_path, optarg, sizeof(cfgfile_path) - 1);
            break;
        default:
            printf("Usage: ./demo -d [device_path] -c [config file path]\n");
            printf("Exp1: ./demo -d /dev/ttyCH343USB0 -c CONFIG.INI\n");
            printf("Exp2: ./demo -d /dev/ttyCH9344USB0 -c CONFIG.INI\n");
            exit(1);
        }
    }

    if (device_path[0] == '\0' || cfgfile_path[0] == '\0') {
        printf("Usage: ./demo -d [device_path] -c [config file path]\n");
        printf("Exp1: ./demo -d /dev/ttyCH343USB0 -c CONFIG.INI\n");
        printf("Exp2: ./demo -d /dev/ttyCH9344USB0 -c CONFIG.INI\n");
        exit(1);
    }

    pcfg = ch34x_cfg_alloc(device_path);
    if (!pcfg) {
        printf("ch34x_cfg_alloc error\n");
        exit(1);
    }

    debug_print_enable(pcfg, true);

    while (1) {
        if (choice != '\n')
            printf("\npress g to get usb config, s to set usb config, d to set default config, q to quit this app.\n");

        scanf("%c", &choice);
        if (choice == 'q')
            break;

        switch (choice) {
        case 'g':
            ret = ch34x_cfg_get(pcfg, &usbCfg, eepBuf, sizeof(eepBuf));
            if (ret < 0) {
                printf("ch34x_cfg_get error, ret:%d\n", ret);
                goto exit;
            }

            print_usb_config(&usbCfg);
            break;
        case 's':
            printf("Setting USB configuration from file:%s...\n", cfgfile_path);
            ret = ch34x_cfg_set(pcfg, cfgfile_path);
            if (ret < 0) {
                printf("ch34x_cfg_set error, ret:%d\n", ret);
                goto exit;
            }
            printf("USB configuration set successfully from file:%s\n", cfgfile_path);
            break;
        case 'd':
            printf("Setting default USB configuration...\n");
            ret = ch34x_cfg_setdef(pcfg);
            if (ret < 0) {
                printf("ch34x_cfg_setdef error, ret:%d\n", ret);
                goto exit;
            }
            printf("Default USB configuration set successfully.\n");
            break;
        default:
            break;
        }
    }

exit:
    ret = ch34x_cfg_free(pcfg);
    if (ret < 0) {
        printf("ch34x_cfg_free error, ret:%d\n", ret);
        exit(0);
    }

    exit(0);
}
