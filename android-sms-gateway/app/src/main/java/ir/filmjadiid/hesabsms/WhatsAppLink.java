package ir.filmjadiid.hesabsms;

import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

/** Official click-to-chat link builder. No SMS or WhatsApp auto-send code. */
public final class WhatsAppLink {
    private WhatsAppLink(){}

    /** Iran 09xxxxxxxxx -> 989xxxxxxxxx. Never guess unknown country codes. */
    public static String internationalPhone(String raw) {
        String phone = raw == null ? "" : raw.trim().replace(" ", "").replace("-", "");
        if (phone.matches("09[0-9]{9}")) return "98" + phone.substring(1);
        if (phone.matches("\\+989[0-9]{9}")) return phone.substring(1);
        if (phone.matches("989[0-9]{9}")) return phone;
        throw new IllegalArgumentException("Invalid Iranian mobile number");
    }

    public static String link(String rawPhone, String message) {
        String phone = internationalPhone(rawPhone);
        if (message == null || message.trim().isEmpty())
            throw new IllegalArgumentException("Message must not be empty");
        String encoded = URLEncoder.encode(message, StandardCharsets.UTF_8)
                .replace("+", "%20");
        return "https://wa.me/" + phone + "?text=" + encoded;
    }

    /** Fallback direct-app scheme when an Android WhatsApp build does not claim wa.me. */
    public static String directAppLink(String rawPhone, String message) {
        String phone = internationalPhone(rawPhone);
        if (message == null || message.trim().isEmpty())
            throw new IllegalArgumentException("Message must not be empty");
        String encoded = URLEncoder.encode(message, StandardCharsets.UTF_8)
                .replace("+", "%20");
        return "whatsapp://send?phone=" + phone + "&text=" + encoded;
    }
}
