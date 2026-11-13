#pragma once

#include <string>
#include <vector>
#include <map>
#include <filesystem>
#include <nlohmann/json.hpp>

namespace dma2ray::state {

struct Profile {
    std::string id;
    std::string name;
    std::string uri;
    std::string subscription_id;
    double created_at = 0.0;
    double updated_at = 0.0;
};

struct Subscription {
    std::string id;
    std::string name;
    std::string url;
    double updated_at = 0.0;
    std::string last_error;
};

class Store {
public:
    explicit Store(const std::filesystem::path& path = "");

    void load();
    void save();

    std::vector<Profile> profiles;
    std::vector<Subscription> subscriptions;
    nlohmann::json settings;

    std::filesystem::path core_path() const;
    void set_setting(const std::string& key, const nlohmann::json& value);
    nlohmann::json get_setting(const std::string& key, const nlohmann::json& default_val = nullptr) const;

    bool get_bool_setting(const std::string& key, bool default_val = false) const;
    int get_int_setting(const std::string& key, int default_val = 0) const;
    double get_double_setting(const std::string& key, double default_val = 0.0) const;
    std::string get_string_setting(const std::string& key, const std::string& default_val = "") const;

    Profile add_profile(const std::string& name, const std::string& uri, const std::string& sub_id = "");
    void remove_profile(const std::string& id);
    Profile* get_profile(const std::string& id);
    void rename_profile(const std::string& id, const std::string& new_name);
    void select_profile(const std::string& id);
    Profile* selected_profile();

    Subscription add_subscription(const std::string& name, const std::string& url);
    void remove_subscription(const std::string& id);
    Subscription* get_subscription(const std::string& id);
    void set_subscription_error(const std::string& id, const std::string& error);
    std::vector<Profile*> profiles_for_subscription(const std::string& sub_id);
    int replace_subscription_profiles(const std::string& sub_id, const std::vector<std::pair<std::string, std::string>>& items);

private:
    std::filesystem::path path_;
    void init_default_settings();
};

} // namespace dma2ray::state
