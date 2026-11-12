#pragma once

#include <gtk/gtk.h>
#include <adwaita.h>
#include <string>

namespace dma2ray::ui {

void apply_theme(const std::string& scheme);
void install_custom_css();

} // namespace dma2ray::ui
