#include <linux/module.h>
#define INCLUDE_VERMAGIC
#include <linux/build-salt.h>
#include <linux/vermagic.h>
#include <linux/compiler.h>

BUILD_SALT;

MODULE_INFO(vermagic, VERMAGIC_STRING);
MODULE_INFO(name, KBUILD_MODNAME);

__visible struct module __this_module
__section(".gnu.linkonce.this_module") = {
	.name = KBUILD_MODNAME,
	.init = init_module,
#ifdef CONFIG_MODULE_UNLOAD
	.exit = cleanup_module,
#endif
	.arch = MODULE_ARCH_INIT,
};

#ifdef CONFIG_RETPOLINE
MODULE_INFO(retpoline, "Y");
#endif

static const struct modversion_info ____versions[]
__used __section("__versions") = {
	{ 0x8044d9a7, "module_layout" },
	{ 0x8e17b3ae, "idr_destroy" },
	{ 0x24a3816e, "usb_deregister" },
	{ 0xc5850110, "printk" },
	{ 0xa6a71d77, "put_tty_driver" },
	{ 0xbf1b30a7, "tty_unregister_driver" },
	{ 0x6237878, "usb_register_driver" },
	{ 0xcd1a0ccc, "tty_register_driver" },
	{ 0xb03705d3, "tty_set_operations" },
	{ 0x67b27ec1, "tty_std_termios" },
	{ 0xe29fe8e9, "__tty_alloc_driver" },
	{ 0x37110088, "remove_wait_queue" },
	{ 0x1000e51, "schedule" },
	{ 0x4afb2238, "add_wait_queue" },
	{ 0xaad8c7d6, "default_wake_function" },
	{ 0xc6cbbc89, "capable" },
	{ 0x6cbbfc54, "__arch_copy_to_user" },
	{ 0x12a4e128, "__arch_copy_from_user" },
	{ 0x88db9f48, "__check_object_size" },
	{ 0xeb233a45, "__kmalloc" },
	{ 0xd94b1375, "tty_flip_buffer_push" },
	{ 0xcd23767e, "tty_insert_flip_string_fixed_flag" },
	{ 0xf45138d1, "tty_standard_install" },
	{ 0x7fa07337, "seq_putc" },
	{ 0x656e4a6e, "snprintf" },
	{ 0x809d7d62, "seq_printf" },
	{ 0x296695f, "refcount_warn_saturate" },
	{ 0x20978fb9, "idr_find" },
	{ 0x4b0a3f52, "gic_nonsecure_priorities" },
	{ 0xaebd1b18, "cpu_hwcaps" },
	{ 0x4c98d79b, "cpu_hwcap_keys" },
	{ 0x14b89635, "arm64_const_caps_ready" },
	{ 0x993a613d, "tty_port_open" },
	{ 0xfe65c5b3, "tty_encode_baud_rate" },
	{ 0x409873e3, "tty_termios_baud_rate" },
	{ 0x6c257ac0, "tty_termios_hw_change" },
	{ 0x41b1f56e, "tty_port_register_device" },
	{ 0x38591a0b, "usb_driver_claim_interface" },
	{ 0xcbd9a678, "usb_register_dev" },
	{ 0x9d4b9649, "usb_alloc_urb" },
	{ 0x2b1fcceb, "usb_alloc_coherent" },
	{ 0x27c5d2d3, "tty_port_init" },
	{ 0x977f511b, "__mutex_init" },
	{ 0xd9a5ea54, "__init_waitqueue_head" },
	{ 0xb8f11603, "idr_alloc" },
	{ 0xbc3a8c69, "usb_get_intf" },
	{ 0x38a9e35f, "usb_ifnum_to_if" },
	{ 0xce283e35, "kmem_cache_alloc_trace" },
	{ 0x2c76de84, "kmalloc_caches" },
	{ 0x6303f42d, "usb_control_msg" },
	{ 0xa85b2d1, "usb_autopm_get_interface" },
	{ 0x3fb9f97f, "tty_port_close" },
	{ 0x86332725, "__stack_chk_fail" },
	{ 0x7aa0d15c, "usb_anchor_urb" },
	{ 0xaea74393, "usb_autopm_get_interface_async" },
	{ 0x4829a47e, "memcpy" },
	{ 0x92540fbf, "finish_wait" },
	{ 0x8ddd8aad, "schedule_timeout" },
	{ 0x8c26d495, "prepare_to_wait_event" },
	{ 0xfe487975, "init_wait_entry" },
	{ 0x530c3045, "tty_port_hangup" },
	{ 0x23974057, "tty_port_tty_wakeup" },
	{ 0x37a0cba, "kfree" },
	{ 0xdcb764ad, "memset" },
	{ 0xbe52880d, "usb_put_intf" },
	{ 0x7665a95b, "idr_remove" },
	{ 0xc5b6f236, "queue_work_on" },
	{ 0x2d3385d3, "system_wq" },
	{ 0x7b0f65e0, "tty_port_tty_hangup" },
	{ 0x6ebe366f, "ktime_get_mono_fast_ns" },
	{ 0x944de879, "usb_find_interface" },
	{ 0x795ee27e, "_dev_info" },
	{ 0xbd5b60f, "usb_driver_release_interface" },
	{ 0xee9f68b6, "usb_free_urb" },
	{ 0xf1331591, "tty_unregister_device" },
	{ 0x6588da8, "tty_kref_put" },
	{ 0xa43d26e4, "tty_vhangup" },
	{ 0xd975fc4e, "tty_port_tty_get" },
	{ 0x3eeb2322, "__wake_up" },
	{ 0x8f889ca1, "usb_deregister_dev" },
	{ 0x6ac0808d, "tty_port_put" },
	{ 0xa36de854, "usb_free_coherent" },
	{ 0x409bcb62, "mutex_unlock" },
	{ 0x2ab7989d, "mutex_lock" },
	{ 0x4b750f53, "_raw_spin_unlock_irq" },
	{ 0x8427cc7b, "_raw_spin_lock_irq" },
	{ 0x9792aa81, "usb_kill_urb" },
	{ 0xf915b4a6, "usb_get_from_anchor" },
	{ 0x35b2494c, "usb_autopm_put_interface" },
	{ 0x705f0309, "usb_autopm_get_interface_no_resume" },
	{ 0x727045f7, "usb_autopm_put_interface_async" },
	{ 0xa03cecda, "_dev_err" },
	{ 0xa1175bbb, "usb_submit_urb" },
	{ 0xd35cce70, "_raw_spin_unlock_irqrestore" },
	{ 0x34db050b, "_raw_spin_lock_irqsave" },
	{ 0x1fdc7df2, "_mcount" },
};

MODULE_INFO(depends, "");

MODULE_ALIAS("usb:v1A86p55D2d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v1A86p55D3d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v1A86p55D5d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v1A86p55D6d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v1A86p55DAd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v1A86p55DBd*dc*dsc*dp*ic*isc*ip*in00*");
MODULE_ALIAS("usb:v1A86p55DDd*dc*dsc*dp*ic*isc*ip*in00*");
MODULE_ALIAS("usb:v1A86p55DEd*dc*dsc*dp*ic*isc*ip*in00*");
MODULE_ALIAS("usb:v1A86p55DEd*dc*dsc*dp*ic*isc*ip*in02*");
MODULE_ALIAS("usb:v1A86p55E7d*dc*dsc*dp*ic*isc*ip*in00*");
MODULE_ALIAS("usb:v1A86p55D8d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v1A86p55D4d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v1A86p55D7d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v1A86p55DFd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v1A86p55E9d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v1A86p55EAd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v1A86p55E8d*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v1A86p55EBd*dc*dsc*dp*ic*isc*ip*in00*");
MODULE_ALIAS("usb:v1A86p55ECd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v1A86p55EFd*dc*dsc*dp*ic*isc*ip*in*");
MODULE_ALIAS("usb:v1A86p5610d*dc*dsc*dp*ic*isc*ip*in01*");

MODULE_INFO(srcversion, "245E7F3F4AE14D0C35B6A2C");
