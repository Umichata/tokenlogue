package io.github.umichata.tokenlogue.qa;

import android.app.Instrumentation;
import android.app.UiAutomation;
import android.app.usage.StorageStatsManager;
import android.content.pm.ApplicationInfo;
import android.os.Build;
import android.os.Process;
import android.os.storage.StorageManager;
import android.os.Bundle;
import android.os.SystemClock;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityEvent;

/** Read only public, allowlisted landmark names on two disposable test packages. */
public final class PublicWindowProbe extends Instrumentation {
    private Bundle options;
    @Override public void onCreate(Bundle args) { super.onCreate(args); options = args; start(); }
    private static final String[] EN = {"Check key", "Providers", "Choose a PIN", "Sign in",
            "Choose a new PIN", "Cancel recovery", "Home", "Tokens", "Spending", "Travel notes"};
    private static final String[] RU = {"Проверить ключ", "Провайдеры", "Выберите PIN", "Войти",
            "Выберите новый PIN", "Отменить восстановление", "Главная", "Токены", "Расходы", "Travel notes"};
    private static void labels(AccessibilityNodeInfo node, String pkg, boolean[] present) {
        if (node == null || !pkg.contentEquals(node.getPackageName())) return;
        if (!node.isPassword() && !"android.widget.EditText".equals(String.valueOf(node.getClassName()))
                && node.isVisibleToUser()) {
            for (CharSequence text : new CharSequence[]{node.getText(), node.getContentDescription()}) {
                if (text == null) continue;
                for(String line : text.toString().split("\\n")) {
                    for (int i=0;i<EN.length;i++) if (line.equals(EN[i]) || line.equals(RU[i])) present[i]=true;
                }
            }
        }
        for (int i=0;i<node.getChildCount();i++) labels(node.getChild(i),pkg,present);
    }
    // Route-only recovery check. Never read text, descriptions, PIN fields or images.
    private String route(AccessibilityNodeInfo node) {
        if (node == null) return "";
        if (!"io.github.umichata.tokenlogue.dart".contentEquals(node.getPackageName())) return "other-window";
        String identifier=node.getViewIdResourceName();
        for (String stage:new String[]{"home","pin","recovery","recovered","key","setup","deletion","loading","error"}) {
            if (("tokenlogue.screen."+stage).equals(identifier)) return stage;
        }
        for (int i=0;i<node.getChildCount();i++) {
            String found=route(node.getChild(i));
            if(!found.isEmpty() && !found.equals("other-window")) return found;
        }
        return "";
    }
    private static void matching(AccessibilityNodeInfo n, String target, String[] choices,
                                 java.util.List<AccessibilityNodeInfo> result, boolean editable) {
        if(n==null || !target.contentEquals(n.getPackageName()) || n.isPassword()) return;
        if(n.isVisibleToUser() && n.isEnabled()){
            if(editable && n.isEditable()) result.add(n);
            if(!editable && !n.isEditable() && n.isClickable()){
                for(CharSequence c:new CharSequence[]{n.getText(),n.getContentDescription()}){
                    if(c==null)continue;
                    for(String line:c.toString().split("\\n")){
                        for(String choice:choices){if(line.equals(choice) && !result.contains(n))result.add(n);}
                    }
                }
            }
        }
        for(int i=0;i<n.getChildCount();i++)matching(n.getChild(i),target,choices,result,editable);
    }

    private void clickPublic(UiAutomation automation,String target,String... choices){
        long end=SystemClock.elapsedRealtime()+7000;
        while(SystemClock.elapsedRealtime()<end){
            if (Build.VERSION.SDK_INT >= 33) automation.clearCache();
            java.util.List<AccessibilityNodeInfo> found=new java.util.ArrayList<>();
            matching(automation.getRootInActiveWindow(),target,choices,found,false);
            if(found.size()==1 && found.get(0).performAction(AccessibilityNodeInfo.ACTION_CLICK)){
                SystemClock.sleep(200);return;
            }
            SystemClock.sleep(100);
        }
        throw new IllegalStateException("public_control");
    }
    @Override public void onStart() {
        Bundle report = new Bundle();
        int code = 0;
        try {
            String target = options.getString("package", "");
            if (!target.equals("io.github.umichata.tokenlogue") && !target.equals("io.github.umichata.tokenlogue.dart"))
                throw new IllegalArgumentException();
            UiAutomation automation = getUiAutomation();
            if ("authored-text".equals(options.getString("measure"))) {
                if(!Build.HARDWARE.matches(".*(ranchu|goldfish).*"))throw new IllegalStateException();
                if(!target.equals("io.github.umichata.tokenlogue.dart"))throw new IllegalStateException();
                String fixture=options.getString("fixture","");
                java.util.Map<String,String> texts=new java.util.HashMap<>();
                texts.put("title-en","Weekend by train");texts.put("title-ru","План поездки");
                texts.put("ask-en","Give a three-item packing list for a weekend train trip. Use a Markdown list.");
                texts.put("ask-ru","Предложи три вещи для поездки на выходные. Ответь коротким списком.");
                texts.put("draft-en","Add a rain jacket to the list.");texts.put("draft-ru","Добавить в список дождевик.");
                String value=texts.get(fixture);if(value==null)throw new IllegalArgumentException();
                SystemClock.sleep(600);
                java.util.List<AccessibilityNodeInfo> fields=new java.util.ArrayList<>();
                AccessibilityNodeInfo active=automation.getRootInActiveWindow();
                String current=route(active);
                if(!current.isEmpty() && !current.equals("home"))throw new IllegalStateException();
                matching(active,target,new String[0],fields,true);
                if(fields.size()!=1)throw new IllegalStateException();
                Bundle arguments=new Bundle();
                arguments.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,value);
                if(!fields.get(0).performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,arguments))throw new IllegalStateException();
                report.putString("authoredTextSet","yes");finish(0,report);return;
            }
            if ("challenge-home".equals(options.getString("measure")) || "challenge-cancel".equals(options.getString("measure")) || "background-recovery".equals(options.getString("measure")) || "route".equals(options.getString("measure"))) {
                if (!target.equals("io.github.umichata.tokenlogue.dart") ||
                    !android.os.Build.HARDWARE.toLowerCase(java.util.Locale.ROOT).matches(".*(ranchu|goldfish).*"))
                    throw new IllegalStateException();
                android.accessibilityservice.AccessibilityServiceInfo info = automation.getServiceInfo();
                info.flags |= android.accessibilityservice.AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS;
                automation.setServiceInfo(info);
                String mode=options.getString("measure");
                boolean watch=!"route".equals(mode);
                if(mode.startsWith("challenge-")){
                    clickPublic(automation,target,"Lock application","Заблокировать приложение");
                    clickPublic(automation,target,"Forgot PIN?","Забыли PIN?");
                    clickPublic(automation,target,"Confirm on device","Подтвердить защиту устройства");
                    Bundle stageReady=new Bundle();stageReady.putString("status","challenge_requested");
                    sendStatus(1,stageReady);
                }
                long start=SystemClock.elapsedRealtime(), end=start+(watch?110000:4000);
                String last=null;
                StringBuilder transitions=new StringBuilder();
                boolean wasRecovered=false;
                final StringBuilder publicClicks = new StringBuilder();
                automation.setOnAccessibilityEventListener(event -> {
                    if(event.getEventType()!=AccessibilityEvent.TYPE_VIEW_CLICKED ||
                        !target.contentEquals(event.getPackageName())) return;
                    AccessibilityNodeInfo source=event.getSource();
                    if(source==null || source.isPassword() ||
                            !"android.widget.Button".contentEquals(source.getClassName())) return;
                    // Inspect the label of an ordinary application button only.
                    // Text fields and Android credential events never enter this path.
                    for(CharSequence name:new CharSequence[]{source.getText(),source.getContentDescription()}){
                        if(name==null)continue;
                        for(String known:new String[]{"Save new PIN","Сохранить новый PIN","Sign in","Войти","Cancel recovery","Отменить восстановление"})
                            if(known.contentEquals(name))synchronized(publicClicks){
                                publicClicks.append(SystemClock.elapsedRealtime()-start).append("=").append(known).append(" ");
                            }
                    }
                });
                while (SystemClock.elapsedRealtime()<end && !wasRecovered) {
                    if(Build.VERSION.SDK_INT>=33)automation.clearCache();
                    String stage=route(automation.getRootInActiveWindow());
                    if(!stage.equals(last)){
                        transitions.append(SystemClock.elapsedRealtime()-start).append("=").append(stage).append(" ");
                        last=stage;
                    }
                    if(!watch && !stage.isEmpty() && !stage.equals("other-window"))break;
                    wasRecovered=stage.equals("recovered");
                    if (!wasRecovered) SystemClock.sleep(80);
                }
                automation.setOnAccessibilityEventListener(null);
                synchronized(publicClicks){ report.putString("publicActionEvents",publicClicks.toString()); }
                report.putString("routeTransitions",transitions.toString());
                if(!watch){finish(0,report);return;}
                report.putString("newPinRouteSeen",wasRecovered?"yes":"no");
                if (wasRecovered) {
                    if("challenge-cancel".equals(mode)){
                        clickPublic(automation,target,"Cancel recovery","Отменить восстановление");
                        report.putString("ordinaryCancelIssued","yes");finish(0,report);return;
                    }
                    try(java.io.InputStream stream=new android.os.ParcelFileDescriptor.AutoCloseInputStream(automation.executeShellCommand("input keyevent KEYCODE_HOME"))){
                        while(stream.read()!=-1){ /* Wait for the one authorised Home action. */ }
                    }
                    report.putString("ordinaryHomeIssued","yes");
                }
                finish(wasRecovered ? 0 : 1,report);
                return;
            }
            if (Build.VERSION.SDK_INT >= 29 && "size".equals(options.getString("measure"))) {
                automation.adoptShellPermissionIdentity("android.permission.PACKAGE_USAGE_STATS");
                try {
                    ApplicationInfo info = getContext().getPackageManager().getApplicationInfo(target,0);
                    StorageStatsManager stats = getContext().getSystemService(StorageStatsManager.class);
                    long bytes=stats.queryStatsForPackage(info.storageUuid == null ? StorageManager.UUID_DEFAULT : info.storageUuid,
                            target, Process.myUserHandle()).getAppBytes();
                    report.putLong("installedApplicationBytes",bytes);
                } finally { automation.dropShellPermissionIdentity(); }
            }
            long until = SystemClock.elapsedRealtime() + 4500;
            boolean[] visible;
            do {
                visible = new boolean[EN.length];
                labels(automation.getRootInActiveWindow(),target,visible);
                boolean found = false;
                for(boolean flag:visible) found |= flag;
                if(found) break;
                SystemClock.sleep(150);
            } while (SystemClock.elapsedRealtime() < until);
            for(int i=0;i<visible.length;i++) report.putString("landmark"+i,visible[i]?"yes":"no");
            report.putString("scope", "Public foreground landmarks, no field values or images");
        } catch (Exception e) {
            code=1; report.putString("error",e.getClass().getSimpleName());
        }
        finish(code,report);
    }
}
