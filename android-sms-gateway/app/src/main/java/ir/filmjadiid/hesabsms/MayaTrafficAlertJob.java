package ir.filmjadiid.hesabsms;

import android.Manifest;
import android.app.job.JobInfo;
import android.app.job.JobParameters;
import android.app.job.JobScheduler;
import android.app.job.JobService;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.os.Build;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

/**
 * Owner-only, opt-in Android system job for Maya RX estimate notifications.
 * The operating system may delay periodic jobs during Doze or power savings.
 * This NEVER sends WhatsApp/SMS, changes VPN state, or modifies server data.
 */
public final class MayaTrafficAlertJob extends JobService {
    private static final int PERIODIC_ID=61201;
    private static final int ONE_SHOT_ID=61202;
    private static final long INTERVAL_MS=15L*60L*1000L;
    private static final String CHANNEL="hesab_maya_low_traffic_v12";
    private static final String PREF="maya_alert_notifications_v12";
    private static final String[] IDS={"maya1","maya-s3","maya4"};
    private static final String[] NAMES={"مایا ۱","مایا ۳","مایا ۴"};

    public static void schedule(Context context){
        if(!Prefs.alertsEnabled(context))return;
        JobScheduler scheduler=(JobScheduler)context.getSystemService(Context.JOB_SCHEDULER_SERVICE);
        if(scheduler==null)return;
        JobInfo info=new JobInfo.Builder(PERIODIC_ID,
                new ComponentName(context,MayaTrafficAlertJob.class))
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                .setPersisted(true)
                .setPeriodic(INTERVAL_MS)
                .build();
        scheduler.schedule(info);
        scheduleImmediate(context);
    }

    public static void scheduleImmediate(Context context){
        if(!Prefs.alertsEnabled(context))return;
        JobScheduler scheduler=(JobScheduler)context.getSystemService(Context.JOB_SCHEDULER_SERVICE);
        if(scheduler==null)return;
        JobInfo info=new JobInfo.Builder(ONE_SHOT_ID,
                new ComponentName(context,MayaTrafficAlertJob.class))
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                .build();
        scheduler.schedule(info);
    }

    public static void cancel(Context context){
        JobScheduler scheduler=(JobScheduler)context.getSystemService(Context.JOB_SCHEDULER_SERVICE);
        if(scheduler!=null){
            scheduler.cancel(PERIODIC_ID);
            scheduler.cancel(ONE_SHOT_ID);
        }
    }


    /** Local-only notification test, never impersonates a real low-traffic event. */
    public static boolean sendTestNotification(Context context){
        if(!Prefs.alertsEnabled(context))return false;
        NotificationManager manager=
                (NotificationManager)context.getSystemService(Context.NOTIFICATION_SERVICE);
        if(manager==null || !manager.areNotificationsEnabled())return false;
        if(Build.VERSION.SDK_INT>=33 &&
                context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                !=PackageManager.PERMISSION_GRANTED)return false;
        NotificationChannel channel=new NotificationChannel(CHANNEL,
                "هشدار کاهش ترافیک مایا",NotificationManager.IMPORTANCE_HIGH);
        manager.createNotificationChannel(channel);
        Intent intent=new Intent(context,MainActivity.class);
        PendingIntent pending=PendingIntent.getActivity(context,61300,intent,
                PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
        Notification note=new Notification.Builder(context,CHANNEL)
                .setSmallIcon(android.R.drawable.stat_notify_error)
                .setContentTitle("آزمایش اعلان حساب VPN")
                .setContentText("این یک اعلان آزمایشی است؛ هیچ سروری زیر ۱۰ گیگ گزارش نشده.")
                .setContentIntent(pending)
                .setAutoCancel(true)
                .build();
        manager.notify(61300,note);
        return true;
    }

    @Override public boolean onStartJob(JobParameters parameters){
        if(!Prefs.alertsEnabled(this))return false;
        Thread work=new Thread(()->{
            try {
                JSONObject doc=readSnapshot();
                handleSnapshot(doc);
            }catch(Exception ignored){
                // Network failures and invalid/stale reports never generate an alert.
            }finally{
                jobFinished(parameters,false);
            }
        },"maya-traffic-alert-check");
        work.start();
        return true;
    }

    @Override public boolean onStopJob(JobParameters parameters){
        // Incomplete background work may resume at a later OS-selected time.
        return true;
    }

    private JSONObject readSnapshot() throws Exception {
        String base=Prefs.baseUrl(this);
        String token=Prefs.token(this);
        if(!base.startsWith("https://")||token.length()<24)
            throw new IllegalStateException("missing authenticated HTTPS gateway");
        URL endpoint=new URL(base+"/sms-gateway/v5/maya/low-traffic");
        HttpURLConnection conn=(HttpURLConnection)endpoint.openConnection();
        conn.setConnectTimeout(7000);
        conn.setReadTimeout(8000);
        conn.setRequestProperty("X-SMS-Gateway-Token",token);
        conn.setRequestProperty("Accept","application/json");
        conn.setUseCaches(false);
        try{
            if(conn.getResponseCode()!=200)
                throw new IllegalStateException("telemetry unavailable");
            try(InputStream input=conn.getInputStream();
                ByteArrayOutputStream bytes=new ByteArrayOutputStream()){
                byte[] buffer=new byte[2048];
                int read;
                while((read=input.read(buffer))!=-1){
                    if(bytes.size()+read>32768)
                        throw new IllegalStateException("response too large");
                    bytes.write(buffer,0,read);
                }
                return new JSONObject(bytes.toString(StandardCharsets.UTF_8.name()));
            }
        }finally{
            conn.disconnect();
        }
    }

    private boolean canNotify(NotificationManager manager){
        if(Build.VERSION.SDK_INT>=33 &&
                checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)
            return false;
        return manager!=null && manager.areNotificationsEnabled();
    }

    private void handleSnapshot(JSONObject doc){
        if(!Prefs.alertsEnabled(this) || !doc.optBoolean("ok",false) ||
                !doc.optBoolean("estimate_only",false) ||
                doc.optDouble("threshold_gb",0)!=10.0)
            return;
        long now=System.currentTimeMillis()/1000L;
        long when=doc.optLong("generated_at",0);
        if(when<=0 || when>now+60 || now-when>180)return;
        JSONObject servers=doc.optJSONObject("servers");
        if(servers==null)return;
        NotificationManager manager=(NotificationManager)getSystemService(NOTIFICATION_SERVICE);
        SharedPreferences flags=getSharedPreferences(PREF,MODE_PRIVATE);
        boolean allowed=canNotify(manager);
        if(allowed && Build.VERSION.SDK_INT>=26){
            NotificationChannel channel=new NotificationChannel(CHANNEL,
                    "هشدار کاهش ترافیک مایا", NotificationManager.IMPORTANCE_HIGH);
            channel.setDescription("هشدار تخمینی زیر ۱۰ گیگ برای سرورهای مایا");
            manager.createNotificationChannel(channel);
        }

        for(int index=0;index<IDS.length;index++){
            String id=IDS[index];
            JSONObject item=servers.optJSONObject(id);
            if(item==null || !"provisional".equals(item.optString("state","")) ||
                    item.optBoolean("is_provider_verified",true))
                continue;
            double remaining=item.optDouble("remaining_gb",Double.NaN);
            if(Double.isNaN(remaining)||Double.isInfinite(remaining)||remaining<0)
                continue;
            boolean warned=flags.getBoolean("warned_"+id,false);
            if(remaining>=12.0){
                flags.edit().putBoolean("warned_"+id,false).apply();
            }else if(remaining<10.0 && !warned && allowed && Prefs.alertsEnabled(this)){
                String title="هشدار ترافیک "+NAMES[index];
                String body="مانده تخمینی: "+String.format(new Locale("fa","IR"),"%.2f",remaining)
                        +" گیگ؛ کمتر از ۱۰ گیگ. مقدار دیتاسنتر تأیید نشده است.";
                Intent open=new Intent(this,MainActivity.class);
                open.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP|Intent.FLAG_ACTIVITY_SINGLE_TOP);
                PendingIntent pending=PendingIntent.getActivity(this,61210+index,open,
                        PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
                Notification note=new Notification.Builder(this,CHANNEL)
                        .setSmallIcon(android.R.drawable.stat_notify_error)
                        .setContentTitle(title)
                        .setContentText(body)
                        .setStyle(new Notification.BigTextStyle().bigText(body))
                        .setContentIntent(pending)
                        .setAutoCancel(true)
                        .setCategory(Notification.CATEGORY_STATUS)
                        .build();
                manager.notify(61210+index,note);
                flags.edit().putBoolean("warned_"+id,true).commit();
            }
        }
    }
}
