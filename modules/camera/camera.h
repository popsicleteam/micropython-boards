#pragma once

// WROVER-KIT PIN Map
#define CAM_PIN_PWDN -1   // power down is not used
#define CAM_PIN_RESET -1  // software reset will be performed
#define CAM_PIN_XCLK 21
#define CAM_PIN_SIOD 26
#define CAM_PIN_SIOC 27

#define CAM_PIN_D7 35
#define CAM_PIN_D6 34
#define CAM_PIN_D5 39
#define CAM_PIN_D4 36
#define CAM_PIN_D3 19
#define CAM_PIN_D2 18
#define CAM_PIN_D1 5
#define CAM_PIN_D0 4
#define CAM_PIN_VSYNC 25
#define CAM_PIN_HREF 23
#define CAM_PIN_PCLK 22

#define XCLK_FREQ_10MHz 10000000
#define XCLK_FREQ_20MHz 20000000

// White Balance
#define WB_NONE 0
#define WB_SUNNY 1
#define WB_CLOUDY 2
#define WB_OFFICE 3
#define WB_HOME 4

// Special Effect
#define EFFECT_NONE 0
#define EFFECT_NEG 1
#define EFFECT_BW 2
#define EFFECT_RED 3
#define EFFECT_GREEN 4
#define EFFECT_BLUE 5
#define EFFECT_RETRO 6
