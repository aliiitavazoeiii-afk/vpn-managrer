package ir.filmjadiid.hesabsms;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.os.IBinder;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class GatewayService extends Service {
    public static final String ACTION_START="ir.filmjadiid.hesabsms.START";
    public static final String ACTION_STOP="ir.filmjadiid.hesabsms.STOP";
    private static final String CHANNEL="hesab_manual_drafts";
    private final ExecutorService executor=Executors.newSingleThreadExecutor();
    private volatile boolean running=false;

    @Override public void onCreate(){
        super.onCreate();
        NotificationChannel channel=new NotificationChannel(CHANNEL,
                "پیامک‌های آماده ارسال",NotificationManager.IMPORTANCE_HIGH);
        getSystemService(NotificationManager.class).createNotificationChannel(channel);
    }

    @Override public int onStartCommand(Intent intent,int flags,int id){
        if(intent!=null && ACTION_STOP.equals(intent.getAction())){
            Prefs.setEnabled(this,false); running=false;stopForeground(STOP_FOREGROUND_REMOVE);stopSelf();
            return START_NOT_STICKY;
        }
        startForeground(4107,notification("دریافت پیش‌نویس‌های سایت",null));
        if(!running){
            running=true;
            executor.execute(()->{
                while(running && Prefs.enabled(this)){
                    try{
                        // Only one unprocessed draft at a time; no network request can send SMS.
                        if(Prefs.hasDraft(this)){
                            // No implicit success when the SMS composer opens.
                            // Only a matching row in Android's sent-SMS provider
                            // can transition debt to waiting.
                            if(Prefs.draftOpenedAt(this)>0L && SentSmsVerifier.permitted(this)) {
                                if(SentSmsVerifier.matchingSentSms(this)){
                                    long idToAck=Prefs.draftId(this);
                                    if(ApiClient.markVerifiedSent(this,idToAck)){
                                        Prefs.clearDraft(this);
                                        getSystemService(NotificationManager.class).cancel(4108);
                                        getSystemService(NotificationManager.class).notify(
                                          4109,notification("پیام ارسالی تأیید شد؛ سایت به‌روزرسانی شد",null));
                                    }
                                    // If HTTP acknowledgement fails, keep pending
                                    // and resend ONLY the acknowledgement, never SMS.
                                }
                            }
                        }else{
                            ApiClient.SmsJob job=ApiClient.pollDraft(this);
                            if(job!=null){
                                if(Prefs.saveDraft(this,job.id,job.phone,job.message)){
                                    getSystemService(NotificationManager.class)
                                        .notify(4108,notification("پیام آماده است؛ برای بازکردن Google Messages لمس کن",job.id));
                                }
                            }
                        }
                    }catch(Exception error){
                        android.util.Log.e("HesabDraft","Cannot fetch draft",error);
                    }
                    try{Thread.sleep(Math.max(5,Prefs.pollSeconds(this))*1000L);}
                    catch(InterruptedException e){break;}
                }
                running=false;
            });
        }
        return START_STICKY;
    }

    private Notification notification(String description,Long jobId){
        Intent intent=new Intent(this,MainActivity.class);
        if(jobId!=null)intent.setAction("ir.filmjadiid.hesabsms.OPEN_DRAFT");
        intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_SINGLE_TOP);
        PendingIntent pi=PendingIntent.getActivity(this,jobId==null?0:1,intent,
             PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
        return new Notification.Builder(this,CHANNEL).setContentTitle("حساب VPN · پیامک دستی")
             .setContentText(description).setSmallIcon(android.R.drawable.stat_notify_chat)
             .setContentIntent(pi).setOngoing(jobId==null).build();
    }
    @Override public void onDestroy(){running=false;executor.shutdownNow();super.onDestroy();}
    @Override public IBinder onBind(Intent i){return null;}
}
