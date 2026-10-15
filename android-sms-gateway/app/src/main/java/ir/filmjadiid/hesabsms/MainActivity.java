package ir.filmjadiid.hesabsms;

import android.Manifest;
import android.app.Activity;
import android.app.NotificationManager;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

public final class MainActivity extends Activity {
    private EditText baseUrl, token;
    private TextView status;

    @Override protected void onCreate(Bundle bundle) {
        super.onCreate(bundle);
        ScrollView scroll=new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(Color.rgb(10,18,31));
        LinearLayout root=new LinearLayout(this);
        root.setPadding(32,44,32,38);
        root.setOrientation(LinearLayout.VERTICAL);
        scroll.addView(root);
        setContentView(scroll);
        title(root,"حساب VPN · ارسال دستی",26);
        title(root,"درخواست سایت به این گوشی می‌رسد. با لمس اعلان، متن در Google Messages آماده می‌شود؛ ارسال فقط با لمس دکمه Send توسط شماست.",15);
        title(root,"آدرس حساب",14);
        baseUrl=field(root,Prefs.baseUrl(this),false);
        title(root,"Gateway Token",14);
        token=field(root,Prefs.token(this),true);
        Button save=button(root,"ذخیره و شروع دریافت پیام‌ها");
        save.setOnClickListener(v->{
            String url=baseUrl.getText().toString().trim();
            if(!url.startsWith("https://")){toast("آدرس باید HTTPS باشد");return;}
            if(token.getText().toString().trim().length()<24){toast("توکن معتبر وارد کن");return;}
            Prefs.setBaseUrl(this,url);
            Prefs.setToken(this,token.getText().toString());
            Prefs.setEnabled(this,true);
            if(Build.VERSION.SDK_INT>=33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                    !=PackageManager.PERMISSION_GRANTED)
                requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS},101);
            Intent service=new Intent(this,GatewayService.class).setAction(GatewayService.ACTION_START);
            if(Build.VERSION.SDK_INT>=26)startForegroundService(service);else startService(service);
            toast("دریافت درخواست فعال شد؛ هیچ SMS خودکاری ارسال نمی‌شود");
            updateStatus();
        });
        title(root,"برای تشخیص اینکه واقعاً Send زده‌ای، برنامه فقط پوشه پیامک‌های ارسالی گوشی را با متن و شماره همین درخواست تطبیق می‌دهد. اطلاعات سایر پیامک‌ها به سرور ارسال نمی‌شود. برای پیام RCS تشخیص خودکار تضمین‌شده نیست.",13);
        Button permission=button(root,"فعال‌سازی تشخیص ارسال (اجازه خواندن SMS)");
        permission.setOnClickListener(v->{
            if(Build.VERSION.SDK_INT>=23 && !SentSmsVerifier.permitted(this)) {
                requestPermissions(new String[]{Manifest.permission.READ_SMS},102);
            } else toast("اجازه خواندن SMS فعال است");
        });
        Button open=button(root,"بازکردن پیام آماده در Google Messages");
        open.setOnClickListener(v->openDraft());
        Button verify=button(root,"بررسی دوباره پیامک ارسالی");
        verify.setOnClickListener(v->verifyNow(true));
        Button skip=button(root,"لغو پیش‌نویس ارسال‌نشده");
        skip.setOnClickListener(v->{
            if(!Prefs.hasDraft(this)){toast("درخواستی برای لغو وجود ندارد");return;}
            new android.app.AlertDialog.Builder(this)
                .setTitle("لغو پیش‌نویس")
                .setMessage("فقط اگر مطمئنی پیامک را نفرستاده‌ای لغو کن؛ این کار مشتری را به در انتظار منتقل نمی‌کند.")
                .setNegativeButton("بازگشت",null)
                .setPositiveButton("لغو درخواست",(dialog,which)->{
                    long id=Prefs.draftId(this);
                    new Thread(()->{
                        boolean ok=ApiClient.cancelDraft(this,id);
                        if(ok)Prefs.clearDraft(this);
                        runOnUiThread(()->{
                            toast(ok?"پیش‌نویس لغو شد":"لغو در سرور تأیید نشد؛ پیش‌نویس باقی ماند");
                            updateStatus();
                        });
                    },"cancel-manual-draft").start();
                }).show();
        });

        Button stop=button(root,"توقف دریافت درخواست‌ها");
        stop.setOnClickListener(v->{
            Prefs.setEnabled(this,false);
            stopService(new Intent(this,GatewayService.class));
            updateStatus();
        });
        Button test=button(root,"آزمایش اتصال به سرور");
        test.setOnClickListener(v->new Thread(()->{
            boolean ok=ApiClient.ping(this);
            runOnUiThread(()->toast(ok?"اتصال برقرار است":"اتصال API برقرار نیست؛ سرور را بررسی کن"));
        }).start());
        status=new TextView(this);
        status.setTextColor(Color.WHITE);
        status.setTextSize(14);
        root.addView(status);
        updateStatus();
        processIncoming(getIntent());
    }
    @Override protected void onNewIntent(Intent i) {
        super.onNewIntent(i);setIntent(i);processIncoming(i);
    }
    @Override protected void onResume(){
        super.onResume();
        if(status!=null)updateStatus();
        if(Prefs.hasDraft(this) && Prefs.draftOpenedAt(this)>0L && SentSmsVerifier.permitted(this))
            verifyNow(false);
    }
    @Override public void onRequestPermissionsResult(int requestCode,String[] permissions,int[] results){
        super.onRequestPermissionsResult(requestCode,permissions,results);
        if(requestCode==102){
            toast(SentSmsVerifier.permitted(this)
                ?"اجازه فعال شد؛ پیام ارسالی بررسی می‌شود"
                :"اجازه خواندن SMS فعال نشد؛ انتقال خودکار انجام نمی‌شود");
            updateStatus();
            if(SentSmsVerifier.permitted(this))verifyNow(false);
        }
    }
    private void verifyNow(boolean announce){
        if(!Prefs.hasDraft(this)||Prefs.draftOpenedAt(this)<=0L){
            if(announce)toast("ابتدا پیش‌نویس را در Google Messages باز کن");
            return;
        }
        if(!SentSmsVerifier.permitted(this)){
            if(announce)toast("مجوز READ_SMS فعال نیست");
            return;
        }
        new Thread(()->{
            boolean found=false,confirmed=false;
            try{
                found=SentSmsVerifier.matchingSentSms(this);
                if(found){
                    long id=Prefs.draftId(this);
                    confirmed=ApiClient.markVerifiedSent(this,id);
                    if(confirmed){
                        Prefs.clearDraft(this);
                        getSystemService(NotificationManager.class).cancel(4108);
                    }
                }
            }catch(Exception error){android.util.Log.w("HesabDraft","SMS verification failed",error);}
            final boolean matched=found,ack=confirmed;
            runOnUiThread(()->{
                updateStatus();
                if(announce||ack)toast(ack
                    ?"ارسال SMS در گوشی تأیید شد؛ سایت به در انتظار منتقل می‌کند"
                    :matched?"پیام ارسالی پیدا شد ولی پاسخ سایت دریافت نشد؛ بعداً دوباره بررسی می‌شود"
                    :"پیامک ارسالی با همین شماره و متن هنوز شناسایی نشده است");
            });
        },"verify-google-sms-sent").start();
    }
    private void processIncoming(Intent i){
        if(i!=null && "ir.filmjadiid.hesabsms.OPEN_DRAFT".equals(i.getAction()))openDraft();
    }
    private void openDraft(){
        if(!Prefs.hasDraft(this)){toast("پیام آماده‌ای وجود ندارد");return;}
        String phone=Prefs.draftPhone(this);
        String message=Prefs.draftMessage(this);
        if(!phone.matches("09[0-9]{9}") || message.isEmpty()){toast("شماره یا پیام نامعتبر است");return;}
        // ACTION_SENDTO delegates composition AND final human send to the SMS app.
        Intent compose=new Intent(Intent.ACTION_SENDTO,Uri.parse("smsto:"+phone));
        compose.putExtra("sms_body",message);
        try{
            long id=Prefs.draftId(this);
            long previousOpen=Prefs.draftOpenedAt(this);
            if(previousOpen<=0L && !Prefs.markDraftOpenedLocally(this,id,System.currentTimeMillis())){
                toast("زمان بازشدن پیش‌نویس ذخیره نشد");return;
            }
            startActivity(compose);
            // Opening Google Messages does NOT mean an SMS was sent.
            new Thread(()->ApiClient.markDraftOpened(getApplicationContext(),id),
                    "draft-opened-ack").start();
            updateStatus();
        }catch(Exception ex){
            toast("برنامه پیامک پیدا نشد؛ Google Messages را پیش‌فرض کن");
        }
    }
    private void updateStatus(){
        if(status!=null)status.setText((Prefs.enabled(this)?"دریافت درخواست فعال":"دریافت درخواست خاموش")
                +(Prefs.hasDraft(this)
                    ?(Prefs.draftOpenedAt(this)>0L
                       ?"\nپیش‌نویس باز شده؛ منتظر شناسایی SMS ارسالی"
                       :"\nیک پیام آماده بازکردن وجود دارد")
                    :"\nپیام آماده‌ای نیست")
                +"\nتشخیص SMS: "+(SentSmsVerifier.permitted(this)?"فعال":"غیرفعال (مجوز لازم است)")
                +"\nDevice ID: "+Prefs.deviceId(this));
    }
    private void title(LinearLayout root,String t,int size){
        TextView v=new TextView(this);
        v.setText(t);v.setTextColor(Color.WHITE);v.setTextSize(size);
        v.setGravity(Gravity.RIGHT);
        v.setPadding(0,18,0,14);
        root.addView(v);
    }
    private EditText field(LinearLayout root,String initial,boolean secret){
        EditText e=new EditText(this);
        e.setText(initial);e.setTextColor(Color.WHITE);
        e.setTextDirection(android.view.View.TEXT_DIRECTION_LTR);
        e.setSingleLine(true);
        e.setInputType(secret?InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD:
                InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_URI);
        root.addView(e,new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,110));
        return e;
    }
    private Button button(LinearLayout root,String caption){
        Button b=new Button(this);b.setText(caption);b.setAllCaps(false);
        root.addView(b,new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,125));
        return b;
    }
    private void toast(String s){Toast.makeText(this,s,Toast.LENGTH_LONG).show();}
}
