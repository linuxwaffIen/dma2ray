#include "dma2ray/config.hpp"

namespace dma2ray::config {

nlohmann::json build_xray_config(
    const vless::VlessProfile& profile,
    bool tun,
    int socks_port,
    int http_port,
    const std::string& log_level,
    const std::string& address_override
) {
    nlohmann::json root;
    root["log"] = {
        {"loglevel", log_level.empty() ? "warning" : log_level}
    };

    nlohmann::json inbounds = nlohmann::json::array();
    if (tun) {
        nlohmann::json tun_in;
        tun_in["tag"] = "tun-in";
        tun_in["port"] = 0;
        tun_in["protocol"] = "tun";
        tun_in["settings"] = {
            {"name", "dma2ray-tun"},
            {"mtu", 9000},
            {"gateway", nlohmann::json::array({"172.19.0.1"})},
            {"dns", nlohmann::json::array({"1.1.1.1", "8.8.8.8"})}
        };
        inbounds.push_back(tun_in);
    } else {
        inbounds.push_back({
            {"tag", "socks-in"},
            {"listen", "127.0.0.1"},
            {"port", socks_port},
            {"protocol", "socks"},
            {"settings", {{"auth", "noauth"}, {"udp", true}}}
        });
        inbounds.push_back({
            {"tag", "http-in"},
            {"listen", "127.0.0.1"},
            {"port", http_port},
            {"protocol", "http"}
        });
    }
    root["inbounds"] = inbounds;

    vless::VlessProfile active_p = profile;
    if (!address_override.empty()) {
        active_p.address = address_override;
    }

    nlohmann::json outbounds = nlohmann::json::array();
    outbounds.push_back(active_p.to_xray_outbound());
    outbounds.push_back({
        {"tag", "direct"},
        {"protocol", "freedom"},
        {"settings", nlohmann::json::object()}
    });
    outbounds.push_back({
        {"tag", "block"},
        {"protocol", "blackhole"},
        {"settings", nlohmann::json::object()}
    });
    root["outbounds"] = outbounds;

    root["routing"] = {
        {"domainStrategy", "AsIs"},
        {"rules", nlohmann::json::array({
            {
                {"type", "field"},
                {"ip", nlohmann::json::array({
                    "geoip:private",
                    "10.0.0.0/8",
                    "172.16.0.0/12",
                    "192.168.0.0/16",
                    "127.0.0.0/8"
                })},
                {"outboundTag", "direct"}
            }
        })}
    };

    return root;
}

} // namespace dma2ray::config
