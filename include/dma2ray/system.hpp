#pragma once

#include <string>

namespace dma2ray::system {

bool is_sysproxy_enabled();
bool set_sysproxy(bool enabled, int http_port = 10809, int socks_port = 10808);

bool is_autostart_enabled();
bool set_autostart(bool enabled);

} // namespace dma2ray::system
