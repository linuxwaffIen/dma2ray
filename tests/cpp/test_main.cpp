#include "dma2ray/vless.hpp"
#include "dma2ray/hysteria.hpp"
#include "dma2ray/config.hpp"
#include "dma2ray/state.hpp"
#include "dma2ray/paths.hpp"

#include <iostream>
#include <cassert>
#include <filesystem>

void test_vless_parsing() {
    std::string uri = "vless://11111111-2222-3333-4444-555555555555@example.com:443?encryption=none&security=reality&sni=example.com&fp=chrome&pbk=123&sid=456&spx=%2F&type=grpc&serviceName=my-service&mode=multi#MyServer";
    auto p = dma2ray::vless::parse_vless(uri);
    assert(p.protocol == "vless");
    assert(p.address == "example.com");
    assert(p.port == 443);
    assert(p.uuid == "11111111-2222-3333-4444-555555555555");
    assert(p.security == "reality");
    assert(p.sni == "example.com");
    assert(p.fp == "chrome");
    assert(p.pbk == "123");
    assert(p.sid == "456");
    assert(p.spx == "/");
    assert(p.network == "grpc");
    assert(p.service_name == "my-service");
    assert(p.mode == "multi");
    assert(p.name == "MyServer");

    auto stream = p.to_xray_stream();
    assert(stream["network"] == "grpc");
    assert(stream["security"] == "reality");
    assert(stream["grpcSettings"]["serviceName"] == "my-service");
    assert(stream["grpcSettings"]["multiMode"] == true);

    auto cfg = dma2ray::config::build_xray_config(p, false, 10808, 10809);
    assert(cfg["inbounds"].size() == 2);
    assert(cfg["outbounds"][0]["protocol"] == "vless");
    std::cout << "[PASS] test_vless_parsing" << std::endl;
}

void test_hysteria_parsing() {
    std::string uri = "hysteria2://my_password@hy.example.com:8443?sni=hy.example.com&insecure=1&obfs=salamander&obfs-password=secret#HyNode";
    auto p = dma2ray::hysteria::parse_hysteria2(uri);
    assert(p.address == "hy.example.com");
    assert(p.port == 8443);
    assert(p.auth == "my_password");
    assert(p.sni == "hy.example.com");
    assert(p.insecure == true);
    assert(p.obfs == "salamander");
    assert(p.obfs_password == "secret");
    assert(p.name == "HyNode");

    std::string yaml = dma2ray::hysteria::format_hysteria_yaml(p, 10808, 10809, false);
    assert(yaml.find("server: hy.example.com:8443") != std::string::npos);
    assert(yaml.find("auth: my_password") != std::string::npos);
    assert(yaml.find("obfs:") != std::string::npos);
    std::cout << "[PASS] test_hysteria_parsing" << std::endl;
}

void test_trojan_shadowsocks() {
    std::string trojan_uri = "trojan://password123@trojan.com:443#TrojanServer";
    auto p_tr = dma2ray::vless::parse_trojan(trojan_uri);
    assert(p_tr.protocol == "trojan");
    assert(p_tr.uuid == "password123");
    assert(p_tr.address == "trojan.com");

    std::string ss_uri = "ss://aes-128-gcm:pass123@ss.com:8388#SSServer";
    auto p_ss = dma2ray::vless::parse_shadowsocks(ss_uri);
    assert(p_ss.protocol == "shadowsocks");
    assert(p_ss.security == "aes-128-gcm");
    assert(p_ss.uuid == "pass123");
    assert(p_ss.address == "ss.com");
    assert(p_ss.port == 8388);
    std::cout << "[PASS] test_trojan_shadowsocks" << std::endl;
}

void test_store_isolated() {
    auto tmp = std::filesystem::temp_directory_path() / "dma2ray_sandbox_test" / "state.json";
    std::filesystem::remove(tmp);

    dma2ray::state::Store store(tmp);
    assert(store.profiles.empty());
    auto p = store.add_profile("TestProf", "vless://test@1.1.1.1:443#TestProf");
    assert(store.profiles.size() == 1);
    assert(store.get_profile(p.id) != nullptr);

    store.set_setting("kernel_mode", "amnezia-xray");
    assert(store.get_setting("kernel_mode") == "amnezia-xray");

    // Reload from file to ensure persistence
    dma2ray::state::Store store2(tmp);
    assert(store2.profiles.size() == 1);
    assert(store2.profiles[0].name == "TestProf");
    assert(store2.get_setting("kernel_mode") == "amnezia-xray");

    std::filesystem::remove_all(tmp.parent_path());
    std::cout << "[PASS] test_store_isolated" << std::endl;
}

void test_flags_and_subscriptions() {
    auto tmp = std::filesystem::temp_directory_path() / "dma2ray_sandbox_test_sub" / "state.json";
    std::filesystem::remove(tmp);

    dma2ray::state::Store store(tmp);
    auto sub = store.add_subscription("MySub", "https://example.com/sub");
    assert(store.subscriptions.size() == 1);
    assert(store.get_subscription(sub.id) != nullptr);

    std::vector<std::pair<std::string, std::string>> items = {
        {"US Node", "vless://uuid@us.node.com:443#US"},
        {"NL Server", "vless://uuid@nl.node.com:443#NL"}
    };
    int count = store.replace_subscription_profiles(sub.id, items);
    assert(count == 2);
    assert(store.profiles.size() == 2);
    assert(store.profiles_for_subscription(sub.id).size() == 2);

    store.rename_profile(store.profiles[0].id, "US Node Renamed");
    assert(store.profiles[0].name == "US Node Renamed");

    store.remove_subscription(sub.id);
    assert(store.subscriptions.empty());
    assert(store.profiles.empty()); // Profiles of removed sub should be deleted

    std::filesystem::remove_all(tmp.parent_path());
    std::cout << "[PASS] test_flags_and_subscriptions" << std::endl;
}

int main() {
    test_vless_parsing();
    test_hysteria_parsing();
    test_trojan_shadowsocks();
    test_store_isolated();
    test_flags_and_subscriptions();
    std::cout << "All C++ native tests passed!" << std::endl;
    return 0;
}
