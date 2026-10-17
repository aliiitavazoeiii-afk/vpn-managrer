import ir.filmjadiid.hesabsms.WhatsAppLink;

/** Plain Java tests, run before Gradle build; no Android, server or SMS dependency. */
public final class WhatsAppLinkTest {
    private static void eq(String actual,String expected){
        if(!expected.equals(actual))throw new AssertionError("expected "+expected+" but got "+actual);
    }
    private static void reject(String phone,String body){
        try{WhatsAppLink.link(phone,body);}
        catch(IllegalArgumentException expected){return;}
        throw new AssertionError("accepted invalid link");
    }
    public static void main(String[] args){
        eq(WhatsAppLink.internationalPhone("09123456789"),"989123456789");
        eq(WhatsAppLink.internationalPhone("+989123456789"),"989123456789");
        eq(WhatsAppLink.internationalPhone("989123456789"),"989123456789");
        eq(WhatsAppLink.link("09123456789","سلام وقت بخیر، اکانتتون تمدید بشه؟"),
            "https://wa.me/989123456789?text=%D8%B3%D9%84%D8%A7%D9%85%20%D9%88%D9%82%D8%AA%20%D8%A8%D8%AE%DB%8C%D8%B1%D8%8C%20%D8%A7%DA%A9%D8%A7%D9%86%D8%AA%D8%AA%D9%88%D9%86%20%D8%AA%D9%85%D8%AF%DB%8C%D8%AF%20%D8%A8%D8%B4%D9%87%D8%9F");
        eq(WhatsAppLink.directAppLink("09123456789","سلام"),
            "whatsapp://send?phone=989123456789&text=%D8%B3%D9%84%D8%A7%D9%85");
        reject("02112345678","سلام");
        reject("09123456789","");
        reject("091234567890","سلام");
        reject("00989123456789","سلام");
        System.out.println("PASS: Iranian 09 -> WhatsApp international phone, Persian UTF-8, no invalid destinations");
    }
}
