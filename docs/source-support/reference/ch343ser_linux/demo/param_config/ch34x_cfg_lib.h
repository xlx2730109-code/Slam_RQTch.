#ifndef CH34X_CFG_LIB_H
#define CH34X_CFG_LIB_H

#include <stdint.h>
#include <stdbool.h>

/*
 * Opaque handle for chip configuration context.
 * The actual struct definition is private to ch34x_cfg_lib.c.
 * External code MUST only use pointers to this type (CH34xCfg_t *).
 */
typedef struct CH34xCfg CH34xCfg_t;

/*----------------------------------------------------------------------
 * USB Configuration Structure
 *----------------------------------------------------------------------*/
typedef struct ch34x_usbConfig {
    uint16_t vendor_id;              /* Vendor ID (e.g. 0x1A86) */
    uint16_t product_id;             /* Product ID (e.g. 0x55D2) */
    int max_power;                   /* Max power consumption in mA (0–500) */
    char power_mode[32];             /* Power mode: "Bus-Powered" or "Self-Powered" */
    bool remote_wakeup;              /* Remote wakeup enabled */
    bool serial_string_enable;       /* Serial number string descriptor enabled (bCfg bit7) */
    bool product_string_enable;      /* Product string descriptor enabled (bCfg bit6) */
    bool manufacturer_string_enable; /* Manufacturer string descriptor enabled (bCfg bit5) */
    char serial_string[64];          /* USB serial number string (≤10 characters) */
    char product_string[64];         /* USB product string (≤18 characters) */
    char manufacturer_string[64];    /* USB manufacturer string (≤18 characters) */
    bool cdc_flow_control;           /* CDC CTS/RTS flow control enabled (bCfg bit4) */
    bool turnOff_SuspendMode_enable; /* Force-disable USB suspend (0xFA in s_dis) */

    bool dtr_mux_tnow_softset_enable; /* CH344/CH348/CH9114 DTR/TNOW soft-set enabled (bCfg bit2) */
    uint8_t dtr_mux_tnow_setbits;     /* CH344/CH348/CH9114 DTR/TNOW mux configuration bits (bDTR, 0x00–0xFF) */

    bool ch9105_gpio_enable;      /* CH9105 GPIO configuration enabled */
    uint16_t ch9105_gpio_setbits; /* CH9105 GPIO mux configuration bits */

    /* ---- CH9101R/Y MODEM pin-mux (bM_S bits 3:0) ---- */
    bool CH9101RY_MODEM_Enable;         /* MODEM mode enabled (bCfg bit1) */
    bool CH9101RY_TXS_MUX_DSR_Enable;   /* TXS mux to DSR (bM_S bit0) */
    bool CH9101RY_RXS_MUX_RI_Enable;    /* RXS mux to RI  (bM_S bit1) */
    bool CH9101RY_TNOW_MUX_DCD_Enable;  /* TNOW mux to DCD (bM_S bit2) */
    bool CH9101RY_SLEEP_MUX_DTR_Enable; /* SLEEP mux to DTR (bM_S bit3) */

    /* ---- CH346C extended configuration ---- */
    bool ch346_config_enable;   /* CH346 extension config enabled */
    uint32_t ch346_config_freq; /* Main frequency (Hz) */
    int ch346_config_mode;      /* Operating mode (0/1/2) */
    int ch346_config_plen;      /* Communication packet length, must be a multiple of 512 */
    int ch346_config_m0_io0;    /* Mode-0 IO0 (PIN12) function */
    int ch346_config_m0_io1;    /* Mode-0 IO1 (PIN13) function */
    int ch346_config_m1_io0;    /* Mode-1 IO0 (PIN15) function */
    int ch346_config_m1_io1;    /* Mode-1 IO1 (PIN16) function */
    int ch346_config_m2_io0;    /* Mode-2 IO0 (PIN13) function */
    int ch346_config_m2_io1;    /* Mode-2 IO1 (PIN15) function */
    int ch346_config_m2_io2;    /* Mode-2 IO2 (PIN16) function */
    int ch346_config_m2_io3;    /* Mode-2 IO3 (PIN17) function */
} usbConfig_t;

/**
 * @brief Allocate and initialize a chip configuration context.
 *     The returned handle is used for all subsequent configuration operations.
 *
 * @param devname The device node path of the target chip, e.g. "/dev/ttyCH343USB0".
 *
 * @return Pointer to the allocated ch34xcfg context on success.
 *         NULL on failure (e.g. out of memory or device not found).
 */
CH34xCfg_t *ch34x_cfg_alloc(const char *devname);

/**
 * @brief Read and retrieve the current chip configuration.
 *
 * @param pcfg Configuration context obtained from ch34x_cfg_alloc().
 * @param usbCfg    [out] Pointer to a usbConfig_t structure to receive the
 *                  parsed configuration.
 * @param eepBuf    [out] Optional raw EEPROM buffer. Pass NULL if not needed.
 * @param eepBufLen Size of eepBuf in bytes (recommended: at least 0x82).
 *
 * @return 0 on success, or a negative error code on failure.
 */
int ch34x_cfg_get(CH34xCfg_t *pcfg, usbConfig_t *usbCfg, uint8_t *eepBuf, int eepBufLen);

/**
 * @brief Write configuration settings to the chip.
 *
 * @param pcfg  Configuration context obtained from ch34x_cfg_alloc().
 * @param cfgfile   Path to the configuration file containing the desired
 *                  settings.
 *
 * @return 0 on success, or a negative error code on failure.
 */
int ch34x_cfg_set(CH34xCfg_t *pcfg, const char *cfgfile);

/**
 * @brief Restore the chip to factory default configuration.
 *
 * @param pcfg  Configuration context obtained from ch34x_cfg_alloc().
 *
 * @return 0 on success, or a negative error code on failure.
 */
int ch34x_cfg_setdef(CH34xCfg_t *pcfg);

/**
 * @brief Release all resources associated with the configuration context.
 *     After this call, the context pointer must not be used again.
 *
 * @param pcfg Configuration context to free.
 *
 * @return 0 on success, or a negative error code on failure.
 */
int ch34x_cfg_free(CH34xCfg_t *pcfg);

/**
 * @brief Enable the debug print function
 *
 * @param pcfg Configuration context obtained from ch34x_cfg_alloc().
 * @param enable true is enable the debug print function or false is close
 */
void debug_print_enable(CH34xCfg_t *pcfg, bool enable);

#endif /* CH34X_CFG_LIB_H */
