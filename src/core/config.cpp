#include "dma2ray/config.hpp"
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>
#include <fstream>

namespace dma2ray::config {

static bool is_ipv6_supported() {
    std::ifstream dis("/proc/sys/net/ipv6/conf/all/disable_ipv6");
    if (dis.is_open()) {
        std::string val;
        dis >> val;
        if (val == "1") return false;
    }

    int fd = socket(AF_INET6, SOCK_DGRAM, 0);
    if (fd < 0) return false;
    struct sockaddr_in6 sa{};
    sa.sin6_family = AF_INET6;
    sa.sin6_addr = in6addr_loopback;
    sa.sin6_port = 0;
    int res = bind(fd, reinterpret_cast<struct sockaddr*>(&sa), sizeof(sa));
    close(fd);
    return res == 0;
}

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
        bool v6 = is_ipv6_supported();
        nlohmann::json gateway = nlohmann::json::array({"172.19.0.1"});
        nlohmann::json routes = nlohmann::json::array({"0.0.0.0/0"});
        if (v6) {
            gateway.push_back("fdfe:dcba:9876::1");
            routes.push_back("::/0");
        }
        nlohmann::json tun_in;
        tun_in["tag"] = "tun-in";
        tun_in["port"] = 0;
        tun_in["protocol"] = "tun";
        tun_in["settings"] = {
            {"name", "dma2ray-tun"},
            {"desc", "Dma2ray TUN"},
            {"mtu", 9000},
            {"gateway", gateway},
            {"dns", nlohmann::json::array({"1.1.1.1", "8.8.8.8"})},
            {"autoSystemRoutingTable", routes},
            {"autoOutboundsInterface", "auto"}
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
