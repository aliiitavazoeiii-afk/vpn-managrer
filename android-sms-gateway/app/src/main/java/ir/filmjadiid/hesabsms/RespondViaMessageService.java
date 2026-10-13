package ir.filmjadiid.hesabsms;

import android.app.Service;
import android.content.Intent;
import android.net.Uri;
import android.telephony.TelephonyManager;
import android.os.IBinder;

/** System-only quick text reply action required by the default SMS role. */
public class RespondViaMessageService extends Service {
    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        try {
            if (intent != null && TelephonyManager.ACTION_RESPOND_VIA_MESSAGE.equals(intent.getAction())) {
                Uri uri = intent.getData();
                CharSequence body = intent.getCharSequenceExtra(Intent.EXTRA_TEXT);
                if (uri != null && body != null) {
                    String phone = Uri.decode(uri.getSchemeSpecificPart());
                    ManualSmsSender.send(this, phone, body.toString());
                }
            }
        } catch (Exception ex) {
            android.util.Log.w("HesabSMS", "System quick reply not sent", ex);
        } finally {
            stopSelf(startId);
        }
        return START_NOT_STICKY;
    }
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
