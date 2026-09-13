if(CONFIG_LVX_USE_DEMO_CONTEST2026_313_EDGE_WALKER)
  nuttx_add_application(
    NAME ew
    SRCS ew_main.c alert_output.c alert_lcd.c alert_buzzer.c ew_ld2451.c ew_wifi_at.c ew_wifi_ui.c ew_llm.c ew_chat.c ew_pinyin.c ew_agent.c ew_agent_tool.c ew_serial_ctl.c ew_mirror.c
    PRIORITY 100
    STACKSIZE 98304
    DEFINITIONS
      SOC_BF0_HCPU
      SF32LB52X
      USE_HAL_DRIVER
    INCLUDE_DIRECTORIES
      ${CMAKE_SOURCE_DIR}/../vendor/sifli/chips/sf32lb52
      ${CMAKE_SOURCE_DIR}/../vendor/sifli/chips/sf32lb52/include
      ${CMAKE_SOURCE_DIR}/../vendor/sifli/chips/drivers/Include
      ${CMAKE_SOURCE_DIR}/../vendor/sifli/chips/drivers/cmsis/Include
      ${CMAKE_SOURCE_DIR}/../vendor/sifli/chips/drivers/cmsis/sf32lb52x
      ${CMAKE_SOURCE_DIR}/../vendor/sifli/chips/boards/include/config/sf32lb52x
      ${CMAKE_SOURCE_DIR}/../vendor/sifli/chips/external/CMSIS/Include
      ${CMAKE_SOURCE_DIR}/../vendor/sifli/boards/sf32lb52/sf32lb52_devkit_lcd/include
    DEPENDS lvgl)
endif()
