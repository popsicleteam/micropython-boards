#include "preview.h"

void esp_vision_preview_init0(void) {
}

void esp_vision_preview_deinit(void) {
}

esp_err_t esp_vision_preview_flush(const image_t* img) {
  (void)img;
  return ESP_ERR_NOT_SUPPORTED;
}
