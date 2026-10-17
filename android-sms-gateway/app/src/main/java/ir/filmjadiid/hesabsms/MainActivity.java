package ir.filmjadiid.hesabsms;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

public final class MainActivity extends Activity {
    private static final int BACKGROUND=0xff0a1220;
    private static final int CARD=0xff182338;
    private static final int OUTLINE=0xff273954;
    private static final int MUTED=0xffabbad0;
    private static final int ACCENT=0xffc5dcff;
    private static final long REFRESH_MS=4000L;

    private final Handler handler=new Handler(Looper.getMainLooper());
    private final ExecutorService io=Executors.newSingleThreadExecutor();
    private final AtomicBoolean fetching=new AtomicBoolean(false);
    private final AtomicBoolean acknowledging=new AtomicBoolean(false);
    private final Runnable periodic=new Runnable(){
        @Override public void run(){
            refresh(false);
            handler.postDelayed(this,REFRESH_MS);
        }
    };

    private EditText baseUrl,token;
    private TextView status,count;
    private LinearLayout messages;
    private ScrollView screen;
    private boolean visible=false;
    private String lastFingerprint="";
    private boolean configSaved=false;

    @Override protected void onCreate(Bundle b){
        super.onCreate(b);
        screen=new ScrollView(this);
        screen.setFillViewport(true);
        screen.setBackgroundColor(BACKGROUND);
        LinearLayout root=new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);
        root.setPadding(dp(18),dp(27),dp(18),dp(34));
        screen.addView(root,new ScrollView.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.WRAP_CONTENT));
        setContentView(screen);

        TextView title=label("پیام‌های آماده واتساپ حساب VPN",24,Color.WHITE,true);
        root.addView(title);
        root.addView(label("همه درخواست‌های سایت یکجا اینجا نمایش داده می‌شوند. هر پیام را جداگانه در واتساپ باز کن و خودت ارسال را بزن.",13,MUTED,false));
        TextView info=label("با زدن «بازکردن پیام»، سایت همان لحظه مشتری را «در انتظار» ثبت می‌کند؛ حتی اگر پیام را ارسال نکنی.",12,ACCENT,false);
        info.setPadding(dp(13),dp(12),dp(13),dp(12));
        info.setBackground(shape(0xff1c3350,OUTLINE,12));
        LinearLayout.LayoutParams infoLp=verticalMargin(dp(15));
        root.addView(info,infoLp);

        LinearLayout settings=block();
        root.addView(settings,verticalMargin(dp(12)));
        settings.addView(label("آدرس سرور",12,MUTED,false));
        baseUrl=new EditText(this);
        setupInput(baseUrl,Prefs.baseUrl(this),false);
        settings.addView(baseUrl);
        settings.addView(label("Gateway Token",12,MUTED,false));
        token=new EditText(this);
        setupInput(token,Prefs.token(this),true);
        settings.addView(token);
        Button save=button("ذخیره و دریافت صف",0xffdbe9ff,0xff12223a);
        settings.addView(save);
        save.setOnClickListener(v->{
            String url=baseUrl.getText().toString().trim();
            String key=token.getText().toString().trim();
            if(!url.startsWith("https://")||key.isEmpty()){
                toast("آدرس HTTPS و توکن لازم است");return;
            }
            Prefs.setBaseUrl(this,url);
            Prefs.setToken(this,key);
            configSaved=true;
            lastFingerprint="";
            refresh(true);
        });

        LinearLayout queueHeader=new LinearLayout(this);
        queueHeader.setOrientation(LinearLayout.VERTICAL);
        root.addView(queueHeader,verticalMargin(dp(18)));
        count=label("صف پیام‌ها",20,Color.WHITE,true);
        queueHeader.addView(count);
        status=label("برای بارگذاری، اطلاعات اتصال را ذخیره کن.",12,MUTED,false);
        queueHeader.addView(status);
        Button reload=button("به‌روزرسانی صف",0xff283a55,Color.WHITE);
        queueHeader.addView(reload);
        reload.setOnClickListener(v->refresh(true));

        messages=new LinearLayout(this);
        messages.setOrientation(LinearLayout.VERTICAL);
        root.addView(messages);
        configSaved=!Prefs.token(this).isEmpty();
    }

    @Override protected void onResume(){
        super.onResume();
        visible=true;
        handler.removeCallbacks(periodic);
        attemptPendingAcknowledgement();
        refresh(true);
        handler.postDelayed(periodic,REFRESH_MS);
    }
    @Override protected void onPause(){
        visible=false;
        handler.removeCallbacks(periodic);
        super.onPause();
    }
    @Override protected void onDestroy(){
        handler.removeCallbacks(periodic);
        io.shutdownNow();
        super.onDestroy();
    }

    private void refresh(boolean force){
        if(!configSaved || !visible)return;
        if(!fetching.compareAndSet(false,true))return;
        if(force)status.setText("در حال دریافت پیام‌های آماده...");
        io.execute(()->{
            ApiClient.Queue queue=null;
            String error=null;
            try{queue=ApiClient.pending(getApplicationContext());}
            catch(Exception ex){error=ex.getMessage();}
            final ApiClient.Queue result=queue;
            final String problem=error;
            runOnUiThread(()->{
                fetching.set(false);
                if(isFinishing()||isDestroyed())return;
                if(problem!=null){
                    status.setText("اتصال برقرار نشد: "+problem);
                    return;
                }
                status.setText("صف متصل است · هنگام بازبودن برنامه هر ۴ ثانیه تازه می‌شود");
                renderQueue(result);
            });
        });
    }

    private void renderQueue(ApiClient.Queue queue){
        long pending=Prefs.pendingOperatorJob(this);
        ArrayList<ApiClient.SmsJob> jobs=new ArrayList<>();
        StringBuilder key=new StringBuilder().append(queue.total).append(':').append(pending);
        for(ApiClient.SmsJob x:queue.drafts){
            if(x.id==pending)continue;
            jobs.add(x);
            key.append(':').append(x.id).append('/').append(x.phone);
        }
        count.setText("پیام‌های آماده: "+queue.total+
            (pending>0?" · ۱ مورد در حال ثبت در سایت":""));
        if(key.toString().equals(lastFingerprint))return;
        lastFingerprint=key.toString();
        int previous=screen.getScrollY();
        messages.removeAllViews();
        if(pending>0){
            TextView pendingNotice=label("یک درخواست بازشده هنوز در سرور تأیید نشده است. اتصال را بررسی کن؛ برنامه خودکار ثبت آن را تکرار می‌کند، نه پیام واتساپ را.",13,0xffffca97,false);
            pendingNotice.setPadding(dp(13),dp(12),dp(13),dp(12));
            pendingNotice.setBackground(shape(0xff412b26,0xff774b36,12));
            messages.addView(pendingNotice,verticalMargin(dp(8)));
            Button retry=button("تلاش مجدد برای ثبت در سایت",0xff483429,Color.WHITE);
            messages.addView(retry);
            retry.setOnClickListener(v->attemptPendingAcknowledgement());
        }
        if(jobs.isEmpty() && pending<0){
            TextView empty=label("فعلاً پیام آماده‌ای در صف نیست.",15,MUTED,false);
            empty.setGravity(Gravity.CENTER);
            empty.setPadding(0,dp(40),0,dp(25));
            messages.addView(empty);
        }
        for(ApiClient.SmsJob job:jobs){
            LinearLayout c=block();
            messages.addView(c,verticalMargin(dp(8)));
            c.addView(label((job.source.equals("debt")?"وصول بدهی":"پیام دستی")
                    +"  ·  درخواست "+job.id,11,ACCENT,true));
            TextView phone=label(job.phone,19,Color.WHITE,true);
            phone.setTextDirection(View.TEXT_DIRECTION_LTR);
            c.addView(phone);
            TextView body=label(job.message,13,MUTED,false);
            body.setMaxLines(5);
            c.addView(body);
            Button open=button("بازکردن پیام آماده در واتساپ",0xffdae8ff,0xff12233c);
            c.addView(open,verticalMargin(dp(8)));
            open.setEnabled(pending<0);
            open.setOnClickListener(v->openMessage(job));
        }
        screen.post(()->screen.scrollTo(0,Math.min(previous,
            Math.max(0,messages.getBottom()-screen.getHeight()+dp(40)))));
    }

    private void openMessage(ApiClient.SmsJob job){
        if(Prefs.pendingOperatorJob(this)>0){
            toast("ابتدا ثبت پیام قبلی در سایت کامل شود");return;
        }
        final String webLink;
        final String appLink;
        try{
            webLink=WhatsAppLink.link(job.phone,job.message);
            appLink=WhatsAppLink.directAppLink(job.phone,job.message);
        }catch(IllegalArgumentException ex){
            toast("شماره موبایل یا متن معتبر نیست");return;
        }
        if(!Prefs.storePendingOperatorJob(this,job.id)){
            toast("ذخیره درخواست انجام نشد");return;
        }
        // Open only a real WhatsApp app, never an SMS composer or a browser.
        // Try normal WhatsApp first, then WhatsApp Business.
        boolean opened=false;
        String[] packages={"com.whatsapp","com.whatsapp.w4b"};
        String[] links={webLink,appLink};
        try{
            for(String pkg:packages){
                for(String link:links){
                    Intent compose=new Intent(Intent.ACTION_VIEW,Uri.parse(link));
                    compose.setPackage(pkg);
                    try{
                        startActivity(compose);
                        opened=true;
                        break;
                    }catch(ActivityNotFoundException ex){
                        // Some installed WhatsApp versions prefer the native scheme.
                    }
                }
                if(opened)break;
            }
            if(!opened){
                Prefs.clearPendingOperatorJob(this,job.id);
                toast("واتساپ نصب نیست یا بازکردن چت پشتیبانی نمی‌شود");
                return;
            }
            // The existing site records operator-open, not message delivery.
            attemptPendingAcknowledgement();
        }catch(Exception ex){
            Prefs.clearPendingOperatorJob(this,job.id);
            toast("واتساپ باز نشد؛ پیام در صف ماند");
        }
    }

    private void attemptPendingAcknowledgement(){
        long id=Prefs.pendingOperatorJob(this);
        if(id<=0 || !acknowledging.compareAndSet(false,true))return;
        new Thread(()->{
            boolean ok=ApiClient.operatorOpened(getApplicationContext(),id);
            if(ok)Prefs.clearPendingOperatorJob(getApplicationContext(),id);
            acknowledging.set(false);
            runOnUiThread(()->{
                if(isFinishing()||isDestroyed())return;
                if(ok){
                    lastFingerprint="";
                    refresh(true);
                }else if(visible)status.setText("ثبت در سایت هنوز تأیید نشده؛ اتصال را بررسی کن");
            });
        },"hesab-operator-ack").start();
    }

    private LinearLayout block(){
        LinearLayout panel=new LinearLayout(this);
        panel.setOrientation(LinearLayout.VERTICAL);
        panel.setPadding(dp(14),dp(12),dp(14),dp(12));
        panel.setBackground(shape(CARD,OUTLINE,16));
        return panel;
    }
    private GradientDrawable shape(int bg,int edge,int r){
        GradientDrawable shape=new GradientDrawable();
        shape.setColor(bg);shape.setCornerRadius(dp(r));shape.setStroke(dp(1),edge);
        return shape;
    }
    private TextView label(String text,int size,int color,boolean strong){
        TextView v=new TextView(this);
        v.setText(text);v.setTextSize(size);v.setTextColor(color);
        v.setGravity(Gravity.RIGHT);
        if(strong)v.setTypeface(null,android.graphics.Typeface.BOLD);
        v.setPadding(0,dp(4),0,dp(7));
        return v;
    }
    private Button button(String text,int background,int foreground){
        Button b=new Button(this);
        b.setText(text);b.setAllCaps(false);b.setTextColor(foreground);
        b.setTextSize(14);b.setBackground(shape(background,background,12));
        return b;
    }
    private void setupInput(EditText e,String initial,boolean secret){
        e.setText(initial);e.setTextColor(Color.WHITE);e.setTextSize(14);
        e.setSingleLine(true);e.setTextDirection(View.TEXT_DIRECTION_LTR);
        e.setInputType(secret?InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD:
                InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_URI);
    }
    private LinearLayout.LayoutParams verticalMargin(int top){
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.WRAP_CONTENT);
        p.topMargin=top;
        return p;
    }
    private int dp(int x){return Math.round(x*getResources().getDisplayMetrics().density);}
    private void toast(String text){Toast.makeText(this,text,Toast.LENGTH_LONG).show();}
}
