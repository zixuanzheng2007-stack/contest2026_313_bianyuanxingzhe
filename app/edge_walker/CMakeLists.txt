if(CONFIG_LVX_USE_DEMO_CONTEST2026_313_EDGE_WALKER)
  nuttx_add_application(
    NAME ew
    SRCS ew_main.c alert_output.c alert_lcd.c ew_ld2451.c
    STACKSIZE 4096)
endif()
