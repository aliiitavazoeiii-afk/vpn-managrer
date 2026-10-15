package ir.filmjadiid.hesabsms;

import android.content.Context;
import android.util.Log;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URLEncoder;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

/** Read-only list plus operator-open acknowledgement. NEVER sends an SMS. */
public final class ApiClient {
    private ApiClient(){}

    public static final class SmsJob {
        public final long id;
        public final String phone;
        public final String message;
        public final String source;
        SmsJob(long id,String phone,String message,String source) {
            this.id=id;this.phone=phone;this.message=message;this.source=source;
        }
    }
    public static final class Queue {
        public final int total;
        public final List<SmsJob> drafts;
        Queue(int total,List<SmsJob> drafts){this.total=total;this.drafts=drafts;}
    }
    private static final class Response {
        final int code;
        final String text;
        Response(int code,String text){this.code=code;this.text=text;}
    }
    private static Response request(Context context,String method,String path,JSONObject body)
            throws Exception {
        URL url=new URL(Prefs.baseUrl(context)+path);
        HttpURLConnection con=(HttpURLConnection)url.openConnection();
        con.setConnectTimeout(7000);
        con.setReadTimeout(9000);
        con.setRequestMethod(method);
        con.setRequestProperty("Accept","application/json");
        con.setRequestProperty("X-SMS-Gateway-Token",Prefs.token(context));
        try{
            if(body!=null){
                byte[] data=body.toString().getBytes(StandardCharsets.UTF_8);
                con.setDoOutput(true);
                con.setRequestProperty("Content-Type","application/json; charset=utf-8");
                con.setFixedLengthStreamingMode(data.length);
                try(OutputStream out=con.getOutputStream()){out.write(data);}
            }
            int code=con.getResponseCode();
            InputStream in=code>=400?con.getErrorStream():con.getInputStream();
            String result="";
            if(in!=null){
                try(InputStream stream=in;ByteArrayOutputStream buf=new ByteArrayOutputStream()){
                    byte[] tmp=new byte[4096];int n;
                    while((n=stream.read(tmp))>=0)if(n>0)buf.write(tmp,0,n);
                    result=buf.toString(StandardCharsets.UTF_8.name());
                }
            }
            return new Response(code,result);
        }finally{con.disconnect();}
    }
    public static Queue pending(Context context) throws Exception {
        String device=URLEncoder.encode(Prefs.deviceId(context),"UTF-8");
        Response r=request(context,"GET","/sms-gateway/v4/drafts/pending?device_id="+device+"&limit=500",null);
        if(r.code!=200)throw new IllegalStateException("HTTP "+r.code+"; "+r.text.substring(0,Math.min(120,r.text.length())));
        JSONObject j=new JSONObject(r.text);
        JSONArray items=j.getJSONArray("drafts");
        ArrayList<SmsJob> jobs=new ArrayList<>();
        for(int k=0;k<items.length();k++){
            JSONObject row=items.getJSONObject(k);
            jobs.add(new SmsJob(row.getLong("id"),row.getString("phone"),
                    row.getString("message"),row.optString("source","manual")));
        }
        return new Queue(j.optInt("total",jobs.size()),jobs);
    }
    public static boolean operatorOpened(Context context,long jobId) {
        try{
            JSONObject j=new JSONObject();
            j.put("device_id",Prefs.deviceId(context));
            Response r=request(context,"POST","/sms-gateway/v4/drafts/"+jobId+"/operator-open",j);
            if(r.code==200)return true;
            Log.w("HesabManual","Operator-open acknowledgement returned HTTP "+r.code);
        }catch(Exception e){Log.w("HesabManual","Cannot acknowledge operator-open",e);}
        return false;
    }
}
