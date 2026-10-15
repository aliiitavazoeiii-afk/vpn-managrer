package ir.filmjadiid.hesabsms;

import android.app.Activity;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.telephony.SmsManager;
import android.util.Log;
import org.json.JSONObject;

import java.util.Map;

/** SMS result receivers are independent of the activity/foreground service.
 * No status callback is considered final until the server acknowledges it.
 * NO automatic retry of an SMS is ever performed here.
 */
public final class SmsStatusReceiver extends BroadcastReceiver {
    public static final String ACTION_SENT = "ir.filmjadiid.hesabsms.SMS_SENT";
    public static final String ACTION_DELIVERED = "ir.filmjadiid.hesabsms.SMS_DELIVERED";
    private static final String STORE = "hesab_native_sms_v2_delivery";
    private static final Object LOCK = new Object();
    private static final String TAG = "HesabSmsRadio";
    private static String explain(int code) {
        if (code == Activity.RESULT_OK) return "SENT_OK";
        if (code == SmsManager.RESULT_ERROR_LIMIT_EXCEEDED) return "ANDROID_SMS_RATE_LIMIT";
        if (code == SmsManager.RESULT_ERROR_RADIO_OFF) return "RADIO_OFF";
        if (code == SmsManager.RESULT_ERROR_NO_SERVICE) return "NO_SERVICE";
        if (code == SmsManager.RESULT_ERROR_GENERIC_FAILURE) return "GENERIC_MODEM_FAILURE";
        if (code == SmsManager.RESULT_RIL_REQUEST_RATE_LIMITED) return "MODEM_RATE_LIMIT";
        if (code == SmsManager.RESULT_RIL_NETWORK_REJECT) return "NETWORK_REJECT";
        if (code == SmsManager.RESULT_RIL_MODEM_ERR) return "MODEM_ERROR";
        return "ANDROID_CODE_" + code;
    }

    private static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences(STORE,Context.MODE_PRIVATE);
    }

    public static void initJob(Context c,long id,int count) {
        synchronized(LOCK) {
            SharedPreferences.Editor ed=prefs(c).edit()
                .putInt("total_"+id,Math.max(1,count))
                .putBoolean("failed_"+id,false);
            for(int i=0;i<count;i++) {
                ed.remove("sent_"+id+"_"+i);
                ed.remove("delivered_"+id+"_"+i);
            }
            if(!ed.commit()) throw new IllegalStateException("Cannot persist SMS multipart state");
        }
    }

    @Override public void onReceive(Context context,Intent intent) {
        final PendingResult pending=goAsync();
        final Context app=context.getApplicationContext();
        final String action=intent.getAction();
        final long id=intent.getLongExtra("job_id",-1L);
        final int part=intent.getIntExtra("part",-1);
        final int total=intent.getIntExtra("total",0);
        final int result=getResultCode();
        final int radioError=intent.getIntExtra("errorCode",-1);
        Log.i(TAG,"callback job="+id+" action="+action+" part="+part+"/"+total
                +" code="+result+" cause="+explain(result)+" radioError="+radioError);
        new Thread(() -> {
          try {
            if (id<=0 || part<0 || total<1 || total>30 || part>=total) return;
            synchronized(LOCK) {
                SharedPreferences p=prefs(app);
                if(p.getInt("total_"+id,0)!=total || p.getBoolean("failed_"+id,false)) return;
                if(ACTION_SENT.equals(action)) {
                    if(result!=Activity.RESULT_OK) {
                        p.edit().putBoolean("failed_"+id,true).commit();
                        Prefs.pause(app,"SMS job "+id+" part "+part+" Android="+result+" ("+explain(result)+") radio="+radioError);
                        reportOrQueue(app,id,"failed",result,total,"Android="+result+" ("+explain(result)+") radio="+radioError);
                        return;
                    }
                    String key="sent_"+id+"_"+part;
                    if(p.getBoolean(key,false)) return; // duplicate PendingIntent callback
                    if(!p.edit().putBoolean(key,true).commit()) {
                        Prefs.pause(app,"Cannot persist SMS callback progress"); return;
                    }
                    if(allParts(p,"sent_"+id+"_",total)) {
                        reportOrQueue(app,id,"sent",0,total,"");
                    }
                } else if(ACTION_DELIVERED.equals(action)) {
                    // Absence of a delivery receipt is not evidence of failure;
                    // sent status and carrier delivery are separate.
                    if(result!=Activity.RESULT_OK) return;
                    String key="delivered_"+id+"_"+part;
                    if(p.getBoolean(key,false))return;
                    p.edit().putBoolean(key,true).commit();
                    if(allParts(p,"delivered_"+id+"_",total))
                        reportOrQueue(app,id,"delivered",0,total,"");
                }
            }
          } finally {pending.finish();}
        },"sms-v2-callback-"+id).start();
    }

    private static boolean allParts(SharedPreferences p,String prefix,int total) {
        for(int i=0;i<total;i++)if(!p.getBoolean(prefix+i,false))return false;
        return true;
    }

    private static void reportOrQueue(Context c,long id,String status,
                                      int code,int parts,String error) {
        try {
            JSONObject j=new JSONObject();
            j.put("id",id);
            j.put("status",status);
            j.put("code",code);
            j.put("parts",parts);
            j.put("error",error);
            String key="pending_"+id+"_"+status;
            // Critical: persist the callback before trying the HTTP request.
            if(!prefs(c).edit().putString(key,j.toString()).commit()){
                Prefs.pause(c,"Cannot persist callback report");return;
            }
            // BroadcastReceiver must not block on a 10–25s HTTP request.
            // Foreground worker uploads this durable status on its next poll.
        } catch(Exception ex){
            Prefs.pause(c,"Cannot store SMS outcome: "+ex.getClass().getSimpleName());
        }
    }

    public static void reportUnknown(Context c,long id,String detail) {
        synchronized(LOCK) {
            int count=prefs(c).getInt("total_"+id,1);
            Prefs.pause(c,"SMS result uncertain: job "+id);
            reportOrQueue(c,id,"uncertain",0,count,detail);
        }
    }

    public static void flushPending(Context c) {
        synchronized(LOCK){
            Map<String,?> all=prefs(c).getAll();
            // Always acknowledge 'sent' before a separately received 'delivered'.
            String[] order={"sent","delivered","failed","uncertain"};
            for(String status:order){
              for(Map.Entry<String,?> e:all.entrySet()){
                if(!e.getKey().startsWith("pending_") ||
                   !e.getKey().endsWith("_"+status) ||
                   !(e.getValue() instanceof String)) continue;
                try{
                    JSONObject j=new JSONObject((String)e.getValue());
                    long id=j.getLong("id");
                    if(ApiClient.reportStatus(c,id,status,
                         j.optString("error",""),Prefs.simId(c),
                         j.optInt("code",0),j.optInt("parts",0))) {
                        prefs(c).edit().remove(e.getKey()).commit();
                        if("sent".equals(status)) Prefs.finish(c,id);
                    }
                } catch(Exception ignored){}
              }
            }
        }
    }
}
