package ir.filmjadiid.hesabsms;

import android.content.Context;
import android.content.SharedPreferences;

import java.util.UUID;

public final class Prefs {
    private static final String NAME = "hesab_sms_gateway";
    private static final String DEFAULT_BASE = "https://hesab.filmjadiid.ir";

    private Prefs() {}

    private static SharedPreferences p(Context c) {
        return c.getSharedPreferences(NAME, Context.MODE_PRIVATE);
    }

    public static String baseUrl(Context c) {
        String v = p(c).getString("base_url", DEFAULT_BASE);
        if (v == null || v.trim().isEmpty()) return DEFAULT_BASE;
        v = v.trim();
        while (v.endsWith("/")) v = v.substring(0, v.length() - 1);
        return v;
    }

    public static void setBaseUrl(Context c, String v) {
        if (v == null) v = DEFAULT_BASE;
        v = v.trim();
        while (v.endsWith("/")) v = v.substring(0, v.length() - 1);
        p(c).edit().putString("base_url", v).apply();
    }

    public static String token(Context c) {
        String v = p(c).getString("token", "");
        return v == null ? "" : v.trim();
    }

    public static void setToken(Context c, String v) {
        p(c).edit().putString("token", v == null ? "" : v.trim()).apply();
    }

    public static String deviceName(Context c) {
        String v = p(c).getString("device_name", "Ali phone");
        return v == null || v.trim().isEmpty() ? "Ali phone" : v.trim();
    }

    public static void setDeviceName(Context c, String v) {
        p(c).edit().putString("device_name", v == null ? "Ali phone" : v.trim()).apply();
    }

    public static String deviceId(Context c) {
        String v = p(c).getString("device_id", "");
        if (v != null && !v.isEmpty()) return v;
        v = "android-" + UUID.randomUUID().toString();
        p(c).edit().putString("device_id", v).apply();
        return v;
    }

    public static int simId(Context c) {
        return p(c).getInt("sim_id", -1);
    }

    public static void setSimId(Context c, int v) {
        p(c).edit().putInt("sim_id", v).apply();
    }

    public static int pollSeconds(Context c) {
        int n = p(c).getInt("poll_seconds", 15);
        return Math.max(5, Math.min(300, n));
    }

    public static void setPollSeconds(Context c, int n) {
        p(c).edit().putInt("poll_seconds", Math.max(5, Math.min(300, n))).apply();
    }

    public static boolean enabled(Context c) {
        return p(c).getBoolean("enabled", false);
    }

    public static void setEnabled(Context c, boolean enabled) {
        p(c).edit().putBoolean("enabled", enabled).apply();
    }
}
