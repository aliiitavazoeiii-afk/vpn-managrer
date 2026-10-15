package ir.filmjadiid.hesabsms;

import android.Manifest;
import android.content.Context;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.provider.Telephony;

/**
 * Only reads SENT SMS rows, and never transmits a message itself.
 * No inbox access, message contents in logs, or upload of SMS history.
 * Matching against the exact preexisting local draft is required.
 * RCS messages are not necessarily recorded in Telephony.Sms.Sent.
 */
public final class SentSmsVerifier {
    private SentSmsVerifier() {}

    public static boolean permitted(Context c) {
        return c.checkSelfPermission(Manifest.permission.READ_SMS)==PackageManager.PERMISSION_GRANTED;
    }

    private static String digits(String s) {
        if (s==null) return "";
        StringBuilder out=new StringBuilder();
        for(int i=0;i<s.length();i++){
            int n=Character.digit(s.charAt(i),10);
            if(n>=0)out.append(n);
        }
        return out.toString();
    }

    private static String phone(String input) {
        String p=digits(input);
        if(p.startsWith("0098"))p="0"+p.substring(4);
        else if(p.startsWith("98") && p.length()==12)p="0"+p.substring(2);
        else if(p.length()==10 && p.startsWith("9"))p="0"+p;
        return p;
    }

    // Provider preserves sent message body but line endings may be normalized.
    private static String body(String raw) {
        return raw==null?"":raw.replace("\r\n","\n").replace('\r','\n');
    }

    public static boolean matchingSentSms(Context c) {
        if(!permitted(c) || !Prefs.hasDraft(c))return false;
        long openedAt=Prefs.draftOpenedAt(c);
        if(openedAt<=0)return false; // never accept preexisting messages
        String expectedPhone=phone(Prefs.draftPhone(c));
        String expectedBody=body(Prefs.draftMessage(c));
        if(expectedBody.isEmpty() || !expectedPhone.matches("09[0-9]{9}"))return false;
        // Fail closed: provider record must be created after the compose screen opened.
        long minDate=openedAt;
        long maxDate=System.currentTimeMillis()+15000L;
        try(Cursor cur=c.getContentResolver().query(
                Telephony.Sms.Sent.CONTENT_URI,
                new String[]{Telephony.Sms.ADDRESS,Telephony.Sms.BODY,Telephony.Sms.DATE},
                Telephony.Sms.DATE+" >= ? AND "+Telephony.Sms.DATE+" <= ?",
                new String[]{String.valueOf(minDate),String.valueOf(maxDate)},
                Telephony.Sms.DATE+" DESC")) {
            if(cur==null)return false;
            int addrIndex=cur.getColumnIndexOrThrow(Telephony.Sms.ADDRESS);
            int bodyIndex=cur.getColumnIndexOrThrow(Telephony.Sms.BODY);
            int dateIndex=cur.getColumnIndexOrThrow(Telephony.Sms.DATE);
            int rows=0;
            while(cur.moveToNext() && ++rows<=100) {
                long sentAt=cur.getLong(dateIndex);
                if(sentAt<openedAt)continue;
                if(expectedPhone.equals(phone(cur.getString(addrIndex)))
                        && expectedBody.equals(body(cur.getString(bodyIndex)))) {
                    return true;
                }
            }
        }
        return false;
    }
}
