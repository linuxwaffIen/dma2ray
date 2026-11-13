#include "dma2ray/state.hpp"
#include "dma2ray/paths.hpp"

#include <fstream>
#include <random>
#include <sstream>
#include <chrono>

namespace dma2ray::state {

static std::string generate_uuid() {
    static std::random_device rd;
    static std::mt19937_64 gen(rd());
    static std::uniform_int_distribution<uint64_t> dis;

    std::ostringstream ss;
    ss << std::hex << dis(gen) << dis(gen);
    return ss.str().substr(0, 32);
}

static double now_seconds() {
    auto now = std::chrono::system_clock::now().time_since_epoch();
    return std::chrono::duration<double>(now).count();
}

void Store::init_default_settings() {
    settings = {
        {"tun_enabled", true},
        {"mode", "vpn"},
        {"socks_port", 10808},
        {"http_port", 10809},
        {"autostart", false},
        {"tray_enabled", true},
        {"auto_connect", false},
        {"selected_profile_id", nullptr},
        {"core_path", ""},
        {"log_level", "warning"},
        {"close_to_tray", true},
        {"ping_timeout", 4.0},
        {"ping_type", "tcp"},
        {"auto_ping", true},
        {"sort_by_latency", false},
        {"kernel_mode", "auto"},
        {"color_scheme", "system"},
        {"auto_update_subs", false},
        {"auto_update_interval", 6}
    };
}

Store::Store(const std::filesystem::path& path) {
    path_ = path.empty() ? paths::state_file() : path;
    init_default_settings();
    load();
}

void Store::load() {
    if (!std::filesystem::exists(path_)) return;
    try {
        std::ifstream f(path_);
        nlohmann::json j;
        f >> j;

        if (j.contains("settings") && j["settings"].is_object()) {
            for (auto& [k, v] : j["settings"].items()) {
                settings[k] = v;
            }
        }

        profiles.clear();
        if (j.contains("profiles") && j["profiles"].is_array()) {
            for (const auto& item : j["profiles"]) {
                Profile p;
                p.id = item.contains("id") && !item["id"].is_null() ? item["id"].get<std::string>() : generate_uuid();
                p.name = item.contains("name") && !item["name"].is_null() ? item["name"].get<std::string>() : "";
                p.uri = item.contains("uri") && !item["uri"].is_null() ? item["uri"].get<std::string>() : "";
                p.subscription_id = item.contains("subscription_id") && !item["subscription_id"].is_null() ? item["subscription_id"].get<std::string>() : "";
                p.created_at = item.value("created_at", 0.0);
                p.updated_at = item.value("updated_at", 0.0);
                profiles.push_back(p);
            }
        }

        subscriptions.clear();
        if (j.contains("subscriptions") && j["subscriptions"].is_array()) {
            for (const auto& item : j["subscriptions"]) {
                Subscription s;
                s.id = item.contains("id") && !item["id"].is_null() ? item["id"].get<std::string>() : generate_uuid();
                s.name = item.contains("name") && !item["name"].is_null() ? item["name"].get<std::string>() : "";
                s.url = item.contains("url") && !item["url"].is_null() ? item["url"].get<std::string>() : "";
                s.updated_at = item.value("updated_at", 0.0);
                s.last_error = item.contains("last_error") && !item["last_error"].is_null() ? item["last_error"].get<std::string>() : "";
                subscriptions.push_back(s);
            }
        }
    } catch (...) {}
}

void Store::save() {
    try {
        std::filesystem::create_directories(path_.parent_path());
        nlohmann::json j;
        j["settings"] = settings;

        nlohmann::json prof_arr = nlohmann::json::array();
        for (const auto& p : profiles) {
            prof_arr.push_back({
                {"id", p.id},
                {"name", p.name},
                {"uri", p.uri},
                {"subscription_id", p.subscription_id.empty() ? nullptr : nlohmann::json(p.subscription_id)},
                {"created_at", p.created_at},
                {"updated_at", p.updated_at}
            });
        }
        j["profiles"] = prof_arr;

        nlohmann::json sub_arr = nlohmann::json::array();
        for (const auto& s : subscriptions) {
            sub_arr.push_back({
                {"id", s.id},
                {"name", s.name},
                {"url", s.url},
                {"updated_at", s.updated_at},
                {"last_error", s.last_error.empty() ? nullptr : nlohmann::json(s.last_error)}
            });
        }
        j["subscriptions"] = sub_arr;

        std::ofstream f(path_);
        f << j.dump(2);
    } catch (...) {}
}

std::filesystem::path Store::core_path() const {
    std::string p = get_setting("core_path", "").get<std::string>();
    return std::filesystem::path(p);
}

void Store::set_setting(const std::string& key, const nlohmann::json& value) {
    settings[key] = value;
    save();
}

nlohmann::json Store::get_setting(const std::string& key, const nlohmann::json& default_val) const {
    if (settings.contains(key)) return settings[key];
    return default_val;
}

bool Store::get_bool_setting(const std::string& key, bool default_val) const {
    if (!settings.contains(key)) return default_val;
    const auto& v = settings[key];
    if (v.is_boolean()) return v.get<bool>();
    if (v.is_number()) return v.get<double>() != 0.0;
    if (v.is_string()) {
        std::string s = v.get<std::string>();
        return s == "true" || s == "1" || s == "yes";
    }
    return default_val;
}

int Store::get_int_setting(const std::string& key, int default_val) const {
    if (!settings.contains(key)) return default_val;
    const auto& v = settings[key];
    if (v.is_number()) return v.get<int>();
    if (v.is_string()) {
        try { return std::stoi(v.get<std::string>()); } catch (...) {}
    }
    return default_val;
}

double Store::get_double_setting(const std::string& key, double default_val) const {
    if (!settings.contains(key)) return default_val;
    const auto& v = settings[key];
    if (v.is_number()) return v.get<double>();
    if (v.is_string()) {
        try { return std::stod(v.get<std::string>()); } catch (...) {}
    }
    return default_val;
}

std::string Store::get_string_setting(const std::string& key, const std::string& default_val) const {
    if (!settings.contains(key)) return default_val;
    const auto& v = settings[key];
    if (v.is_string()) return v.get<std::string>();
    if (v.is_null()) return default_val;
    return v.dump();
}

Profile Store::add_profile(const std::string& name, const std::string& uri, const std::string& sub_id) {
    Profile p;
    p.id = generate_uuid();
    p.name = name;
    p.uri = uri;
    p.subscription_id = sub_id;
    p.created_at = now_seconds();
    p.updated_at = p.created_at;
    profiles.push_back(p);
    save();
    return p;
}

void Store::remove_profile(const std::string& id) {
    profiles.erase(std::remove_if(profiles.begin(), profiles.end(), [&](const Profile& p) {
        return p.id == id;
    }), profiles.end());
    save();
}

Profile* Store::get_profile(const std::string& id) {
    for (auto& p : profiles) {
        if (p.id == id) return &p;
    }
    return nullptr;
}

void Store::rename_profile(const std::string& id, const std::string& new_name) {
    auto* p = get_profile(id);
    if (p) {
        p->name = new_name;
        p->updated_at = now_seconds();
        save();
    }
}

void Store::select_profile(const std::string& id) {
    set_setting("selected_profile_id", id);
}

Profile* Store::selected_profile() {
    auto sel = get_setting("selected_profile_id", "");
    if (sel.is_string()) {
        std::string id = sel.get<std::string>();
        auto* p = get_profile(id);
        if (p) return p;
    }
    if (!profiles.empty()) {
        return &profiles.front();
    }
    return nullptr;
}

Subscription Store::add_subscription(const std::string& name, const std::string& url) {
    Subscription s;
    s.id = generate_uuid();
    s.name = name;
    s.url = url;
    s.updated_at = now_seconds();
    subscriptions.push_back(s);
    save();
    return s;
}

void Store::remove_subscription(const std::string& id) {
    subscriptions.erase(std::remove_if(subscriptions.begin(), subscriptions.end(), [&](const Subscription& s) {
        return s.id == id;
    }), subscriptions.end());

    profiles.erase(std::remove_if(profiles.begin(), profiles.end(), [&](const Profile& p) {
        return p.subscription_id == id;
    }), profiles.end());
    save();
}

Subscription* Store::get_subscription(const std::string& id) {
    for (auto& s : subscriptions) {
        if (s.id == id) return &s;
    }
    return nullptr;
}

void Store::set_subscription_error(const std::string& id, const std::string& error) {
    auto* s = get_subscription(id);
    if (s) {
        s->last_error = error;
        save();
    }
}

std::vector<Profile*> Store::profiles_for_subscription(const std::string& sub_id) {
    std::vector<Profile*> res;
    for (auto& p : profiles) {
        if (p.subscription_id == sub_id) res.push_back(&p);
    }
    return res;
}

int Store::replace_subscription_profiles(const std::string& sub_id, const std::vector<std::pair<std::string, std::string>>& items) {
    // Remove existing for this sub
    profiles.erase(std::remove_if(profiles.begin(), profiles.end(), [&](const Profile& p) {
        return p.subscription_id == sub_id;
    }), profiles.end());

    double t = now_seconds();
    int count = 0;
    for (const auto& [name, uri] : items) {
        Profile p;
        p.id = generate_uuid();
        p.name = name;
        p.uri = uri;
        p.subscription_id = sub_id;
        p.created_at = t;
        p.updated_at = t;
        profiles.push_back(p);
        count++;
    }

    auto* s = get_subscription(sub_id);
    if (s) {
        s->updated_at = t;
        s->last_error = "";
    }
    save();
    return count;
}

} // namespace dma2ray::state
