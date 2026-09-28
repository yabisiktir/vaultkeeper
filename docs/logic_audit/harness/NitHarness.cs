// Headless NIT harness (logic audit, stage 0).
//
// Loads the ORIGINAL "NWN Installer Tool.exe" as a library inside the CrossOver
// bottle, points its settings at the sandbox built by make_sandbox.sh, replays
// NIT's own start-up (NIT_Load) without showing the window, then answers
// queries read from C:\nitdiff\in.tsv (one "command<TAB>arg" per line) into
// C:\nitdiff\out.tsv ("command<TAB>arg<TAB>result").
//
// Safety: My.Settings is keyed by the entry program, so this harness never
// touches NIT's own user.config. Before start-up runs, the sandbox is checked
// with NIT's own validators; if it would fall back to Documents\Neverwinter
// Nights (the owner's REAL folder via the bottle's symlink) we abort.
//
// Build (on the Mac): mcs -r:System.Windows.Forms.dll NitHarness.cs -out:NitHarness.exe
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Threading;
using System.Windows.Forms;

class NitHarness
{
    const string Root = @"C:\nitdiff";
    const string Sb = Root + @"\sb";
    const BindingFlags All = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.Instance;

    static StreamWriter log;
    static string phase = "init";
    static Assembly nit;

    static void Log(string s) { log.WriteLine(DateTime.Now.ToString("HH:mm:ss.fff") + " [" + phase + "] " + s); log.Flush(); }

    static Type T(string name) { return nit.GetTypes().First(t => t.Name == name); }
    static object Settings() { return T("MySettings").GetProperty("Default", All).GetValue(null); }
    static void Set(string prop, object value)
    {
        var s = Settings(); s.GetType().GetProperty(prop, All).SetValue(s, value);
        Log("setting " + prop + " = " + value);
    }
    static object Get(string prop) { var s = Settings(); return s.GetType().GetProperty(prop, All).GetValue(s); }
    static object CallStatic(string type, string method, params object[] args)
    {
        var m = T(type).GetMethods(All).First(x => x.Name == method && x.GetParameters().Length == args.Length);
        return m.Invoke(null, args);
    }

    [STAThread]
    static int Main(string[] args)
    {
        Directory.CreateDirectory(Root);
        log = new StreamWriter(Path.Combine(Root, "harness.log"), false);
        // Not a command-line argument: NIT parses the process command line itself.
        var wdEnv = Environment.GetEnvironmentVariable("NITDIFF_WATCHDOG");
        int watchdogSeconds = string.IsNullOrEmpty(wdEnv) ? 120 : int.Parse(wdEnv);
        var wd = new Thread(() =>
        {
            Thread.Sleep(watchdogSeconds * 1000);
            Log("WATCHDOG: still in phase '" + phase + "' after " + watchdogSeconds + "s; open forms: " +
                string.Join(", ", Application.OpenForms.Cast<Form>().Select(f => f.GetType().Name + "('" + f.Text + "')")));
            foreach (Form f in Application.OpenForms.Cast<Form>().ToList())
                Log("  form " + f.GetType().Name + " texts: " + Texts(f));
            Environment.Exit(3);
        }) { IsBackground = true };
        wd.Start();

        try
        {
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.ThrowException);
            phase = "load-assembly";
            nit = Assembly.LoadFrom("NWN Installer Tool.exe");
            Log("loaded " + nit.FullName);

            phase = "settings";
            string version = nit.GetName().Version.ToString();
            Set("PathNit", Sb + @"\store");
            Set("PathExtendedEditionUser", Sb + @"\user");
            Set("PathExtendedEditionLib", Sb + @"\eelib");
            Set("PathGameSaves", Sb + @"\user\saves");
            Set("PathTemp", Sb + @"\temp");
            Set("PathDownloads", Sb + @"\downloads");
            Set("PathStartupSound", "");
            Set("PrivateOriginalDisabled", true);
            Set("PrivateCurrentVersion", version);
            Set("PrivatePreviousVersion", version);   // not a first-time run: avoids opening the help file

            phase = "guard";
            bool userOk = (bool)CallStatic("Paths", "ValidateExtendedUser", Sb + @"\user");
            bool libOk = (bool)CallStatic("Paths", "ValidateExtendedLib", Sb + @"\eelib");
            Log("sandbox user valid=" + userOk + ", lib valid=" + libOk);
            if (!userOk || !libOk) { Log("ABORT: sandbox invalid, NIT would fall back to the real folders"); return 2; }

            // Auto-responder: answers NIT's modal dialogs from dialog_rules.tsv, logging each one.
            var rules = File.ReadAllLines(Path.Combine(Root, "dialog_rules.tsv"))
                .Where(l => l.Trim() != "" && !l.StartsWith("#")).Select(l => l.Split(new[] { '\t' })).ToList();
            var responder = new System.Windows.Forms.Timer { Interval = 250 };
            var answered = new HashSet<Form>();
            responder.Tick += (o, e) =>
            {
                foreach (Form f in Application.OpenForms.Cast<Form>().ToList())
                {
                    if (!f.Modal || answered.Contains(f)) continue;
                    string text = f.GetType().Name + ": " + Texts(f);
                    var rule = rules.FirstOrDefault(r => text.IndexOf(r[0], StringComparison.OrdinalIgnoreCase) >= 0);
                    if (rule == null) { Log("DIALOG (no rule, aborting): " + text); Environment.Exit(4); }
                    if (rule[1] == "-") continue;   // known progress window: let it finish
                    // "*" = dismiss (screen parity: a form's Load may put up a message).
                    var button = rule[1] != "*" ? FindButton(f, rule[1])
                        : new[] { "OK", "Cancel", "No", "Close", "Continue" }.Select(b => FindButton(f, b)).FirstOrDefault(b => b != null);
                    if (button == null) { Log("DIALOG rule matched but no button '" + rule[1] + "': " + text); Environment.Exit(4); }
                    if (rule.Length > 3 && rule[3] != "")   // text to type into the first empty-able TextBox
                    {
                        var tb = FindText(f);
                        if (tb == null) { Log("DIALOG rule matched but no text box: " + text); Environment.Exit(4); }
                        tb.Text = rule[3];
                    }
                    if (rule.Length > 2 && rule[2] != "")
                    {
                        var radio = FindRadio(f, rule[2]);
                        if (radio == null) { Log("DIALOG rule matched but no option '" + rule[2] + "': " + text); Environment.Exit(4); }
                        radio.Checked = true;
                    }
                    answered.Add(f); DialogsAnswered++;
                    Log("DIALOG answered '" + rule[1] + (rule.Length > 2 ? " / " + rule[2] : "") + "': " + text);
                    button.PerformClick();
                }
            };
            responder.Start();

            // LazWorks FileOperations race (see stage2 findings): a worker that has just
            // found the queue empty is still IsBusy when the UI thread queues the next item,
            // so RunOperationWorkers skips it and the item is never processed. Patch: when a
            // worker completes with items still queued, restart the workers. Logged each time.
            var patched = new HashSet<object>();
            var raceFix = new System.Windows.Forms.Timer { Interval = 10 };
            raceFix.Tick += (o, e) =>
            {
                foreach (Form f in Application.OpenForms.Cast<Form>().ToList())
                {
                    if (f.GetType().Name != "FileOperations" || patched.Contains(f)) continue;
                    patched.Add(f);
                    var ft = f.GetType();
                    var workers = ft.GetField("Workers", All)?.GetValue(f) as System.Collections.IEnumerable;
                    var queue = ft.GetField("WorkerQueue", All)?.GetValue(f) as System.Collections.ICollection;
                    var run = ft.GetMethod("RunOperationWorkers", All);
                    if (workers == null || queue == null || run == null) { Log("race patch: FileOperations members not found"); continue; }
                    foreach (var w in workers)
                    {
                        var bgw = (System.ComponentModel.BackgroundWorker)w.GetType().GetProperty("Worker", All).GetValue(w);
                        bgw.RunWorkerCompleted += (s2, e2) =>
                        {
                            if (queue.Count > 0) { Log("race patch: restarting workers, " + queue.Count + " item(s) still queued"); run.Invoke(f, null); }
                        };
                    }
                }
            };
            raceFix.Start();

            phase = "nit-load";
            // Under Wine, Environment.GetFolderPath(ProgramFiles) is empty and LazWorks'
            // WordPad lookup throws inside the form constructor. WordPad is only a
            // "open with" target, so record it as not installed.
            var lazDefs = AppDomain.CurrentDomain.GetAssemblies().Concat(new[] { Assembly.LoadFrom("LazWorks.Library.dll") })
                .SelectMany(a => { try { return a.GetTypes(); } catch (ReflectionTypeLoadException x) { return x.Types.Where(t => t != null).ToArray(); } })
                .First(t => t.GetField("WordPadPathValue", All) != null);
            lazDefs.GetField("WordPadPathValue", All).SetValue(null, "");
            Log("WordPad path preset to none (" + lazDefs.FullName + ")");

            // The real app initialises Defs before the main form exists; Defs's static
            // constructor creates the form itself, so trigger it first and reuse that form.
            System.Runtime.CompilerServices.RuntimeHelpers.RunClassConstructor(T("Defs").TypeHandle);
            var myProject = T("MyProject");
            var forms = myProject.GetProperty("Forms", All).GetValue(null);
            var form = forms.GetType().GetProperty("NIT", All).GetValue(forms);
            Log("form constructed: " + form.GetType().FullName);
            // Run the form normally: Load then Shown fire exactly as in the real app.
            // Our Shown handler is added after NIT's own, so it runs once the profile is loaded.
            var nitForm = (Form)form;
            nitFormRef = nitForm;

            // Replay MyApplication_Startup (ApplicationEvents.vb): splash progress flag + splash screen.
            var defsT = T("Defs");
            var progressPrefs = defsT.GetProperty("ProgressBarPrefs", All)?.GetValue(null) ?? defsT.GetField("ProgressBarPrefs", All)?.GetValue(null);
            bool showSplash = progressPrefs != null && Convert.ToInt32(progressPrefs) != 0;
            var ssp = (MemberInfo)defsT.GetProperty("ShowSplashProgressBar", All) ?? defsT.GetField("ShowSplashProgressBar", All);
            if (ssp is PropertyInfo) ((PropertyInfo)ssp).SetValue(null, showSplash); else ((FieldInfo)ssp).SetValue(null, showSplash);
            var cmspProp = nitForm.GetType().GetProperty("CommonMsp", All);
            var splash = Activator.CreateInstance(cmspProp.PropertyType, new object[] { showSplash });
            cmspProp.SetValue(nitForm, splash);
            splash.GetType().GetMethods(All).First(m => m.Name == "Show" && m.GetParameters().Length == 3)
                .Invoke(splash, new object[] { nitForm, "The Installer Tool is getting ready...", 20 });
            Log("startup splash replayed (progress bar=" + showSplash + ")");
            int result = 0;
            nitForm.Shown += (o, e) =>
            {
                try
                {
                    phase = "post-load-guard";
                    string userPath = (string)T("Paths").GetProperty("ExtendedUserPath", All).GetValue(null);
                    string tool = (string)T("Paths").GetProperty("Tool", All).GetValue(null);
                    Log("Paths.ExtendedUserPath=" + userPath + "  Paths.Tool=" + tool);
                    if (!userPath.StartsWith(Sb, StringComparison.OrdinalIgnoreCase) || !tool.StartsWith(Sb, StringComparison.OrdinalIgnoreCase))
                    { Log("ABORT: NIT resolved paths outside the sandbox"); result = 2; }
                    else { phase = "queries"; RunQueries(); phase = "done"; }
                }
                catch (Exception x) { Log("FAIL in queries: " + x); result = 1; }
                log.Flush();
                Environment.Exit(result);
            };
            Application.Run(nitForm);
            Log("form closed before Shown completed");
            return 5;
        }
        catch (Exception e)
        {
            Log("FAIL: " + (e is TargetInvocationException && e.InnerException != null ? e.InnerException : e));
            return 1;
        }
    }

    static string Texts(Control c)
    {
        var parts = new List<string>();
        foreach (Control k in c.Controls) { if (!string.IsNullOrWhiteSpace(k.Text)) parts.Add(k.Text.Replace("\r", " ").Replace("\n", " ")); var sub = Texts(k); if (sub != "") parts.Add(sub); }
        return string.Join(" | ", parts);
    }

    // title<TAB>path.to.property<TAB>value ; lists/dicts are sorted and joined so order never counts
    static void Flatten(string title, string prefix, object obj, List<string> lines, int depth)
    {
        if (obj == null || depth > 4) return;
        foreach (var pr in obj.GetType().GetProperties(BindingFlags.Public | BindingFlags.Instance))
        {
            if (pr.GetIndexParameters().Length > 0) continue;
            object v; try { v = pr.GetValue(obj); } catch { continue; }
            string name = prefix + pr.Name;
            if (v == null || v is string || v.GetType().IsPrimitive || v is Enum) { lines.Add(title + "\t" + name + "\t" + Convert.ToString(v)); continue; }
            var dict = v as System.Collections.IDictionary;
            if (dict != null)
            {
                var items = new List<string>();
                foreach (System.Collections.DictionaryEntry de in dict)
                    items.Add(de.Key + ":" + (de.Value is string || !(de.Value is System.Collections.IEnumerable) ? Convert.ToString(de.Value)
                        : string.Join(",", ((System.Collections.IEnumerable)de.Value).Cast<object>().Select(Convert.ToString).OrderBy(x => x, StringComparer.OrdinalIgnoreCase))));
                lines.Add(title + "\t" + name + "\t" + string.Join("|", items.OrderBy(x => x, StringComparer.OrdinalIgnoreCase)));
                continue;
            }
            var list = v as System.Collections.IEnumerable;
            if (list != null)
            {
                var items = list.Cast<object>().Select(x => x == null || x is string || x.GetType().IsPrimitive ? Convert.ToString(x) : Describe(x));
                lines.Add(title + "\t" + name + "\t" + string.Join("|", items.OrderBy(x => x, StringComparer.OrdinalIgnoreCase)));
                continue;
            }
            Flatten(title, name + ".", v, lines, depth + 1);
        }
    }

    static string Describe(object o)
    {
        return "{" + string.Join(";", o.GetType().GetProperties(BindingFlags.Public | BindingFlags.Instance)
            .Where(p => p.GetIndexParameters().Length == 0 && (p.PropertyType == typeof(string) || p.PropertyType.IsPrimitive || p.PropertyType.IsEnum))
            .Select(p => { try { return p.Name + "=" + p.GetValue(o); } catch { return p.Name + "=?"; } })) + "}";
    }

    // ------------------------------------------------------------------ stage 2
    static Form nitFormRef;
    static StreamWriter snaps;
    static object Member(object o, string name)   // property or field, instance or static
    {
        var t = o as Type ?? o.GetType(); var inst = o is Type ? null : o;
        var pr = t.GetProperty(name, All); if (pr != null && pr.GetIndexParameters().Length == 0) return pr.GetValue(inst);
        var f = t.GetField(name, All); if (f != null) return f.GetValue(inst);
        throw new MissingMemberException(t.Name, name);
    }
    static object Pd() { return T("Defs").GetField("pd", All).GetValue(null); }
    static object CallForm(string name, params object[] args)
    {
        var m = nitFormRef.GetType().GetMethods(All).First(x => x.Name == name && x.GetParameters().Length == args.Length);
        return m.Invoke(nitFormRef, args);
    }
    static object CallFormOpt(string name, params object[] args)   // fills optional parameters
    {
        var m = nitFormRef.GetType().GetMethods(All).First(x => x.Name == name && x.GetParameters().Length >= args.Length);
        var full = m.GetParameters().Select((p, i) => i < args.Length ? args[i] : p.DefaultValue).ToArray();
        return m.Invoke(nitFormRef, full);
    }

    // "@stem" = the mod NIT creates when a source with that name is pasted.
    static string ResolveMod(string x)
    {
        if (!x.StartsWith("@")) return x;
        var mpi = T("NIT").GetNestedType("ModPasteInfo", All);
        var o = Activator.CreateInstance(mpi, All, null, new object[] { "Group", x.Substring(1) }, null);
        return Convert.ToString(mpi.GetProperty("ModName", All).GetValue(o));
    }

    static string RunScenario(string script)
    {
        string user = Sb + @"\user", fixtures = Root + @"\fixtures";
        snaps = new StreamWriter(Path.Combine(Root, "snaps.tsv"), false);
        Snapshot("00 start");
        int n = 0;
        foreach (var raw in File.ReadAllLines(script))
        {
            if (raw.Trim() == "" || raw.StartsWith("#")) continue;
            var a = raw.Split(new[] { '\t' }); string op = a[0];
            var list = a.Length > 1 ? a[1].Split(new[] { '|' }).Select(ResolveMod).ToList() : new List<string>();
            for (int i = 1; i < a.Length; i++) if (a[i].StartsWith("@")) a[i] = ResolveMod(a[i]);
            n++; string step = n.ToString("00") + " " + raw.Replace('\t', ' ');
            Log("STEP " + step);
            try
            {
                switch (op)
                {
                    case "paste":
                    {
                        var m = nitFormRef.GetType().GetMethod("ModPaste", All);
                        var iop = m.GetParameters()[2].ParameterType;
                        string groupNone = Convert.ToString(T("Pdc").GetField("GroupNone", All).GetValue(null));
                        m.Invoke(nitFormRef, new object[] { groupNone, list.Select(x => Path.Combine(fixtures, x)).ToList(), Enum.Parse(iop, "Copying") });
                        break;
                    }
                    case "create_installer": CallForm("PerformCreateInstaller", list); break;
                    case "set_dependency":
                    {
                        var pd = Pd();
                        var ip = pd.GetType().GetProperties(All).First(x => x.Name == "ModItem" && x.GetIndexParameters().Length == 1 && x.GetIndexParameters()[0].ParameterType == typeof(string));
                        var mdi = ip.GetValue(pd, new object[] { a[1] });
                        var deps = (List<string>)mdi.GetType().GetProperty("Dependencies", All).GetValue(mdi);
                        deps.Add(a[2]);
                        break;
                    }
                    case "install": CallForm("InstallMods", list); break;
                    case "uninstall": CallFormOpt("UninstallMods", list, true); break;
                    case "edit_mod":   // edit_mod <mod> <relative path in mod folder> <content | DELETE>
                    {
                        string mods = (string)Member(T("Paths"), "ProfileMods");
                        var target = Path.Combine(mods, a[1], a[2].Replace('/', '\\'));
                        if (a[3] == "DELETE") File.Delete(target); else { Directory.CreateDirectory(Path.GetDirectoryName(target)); File.WriteAllText(target, a[3]); }
                        break;
                    }
                    case "create_restorer":   // the real menu click; the name dialog is answered by rule
                        CallForm("MsCreateRestorer_Click", nitFormRef, EventArgs.Empty);
                        break;
                    case "external_delete": File.Delete(Path.Combine(user, a[1].Replace('/', '\\'))); break;
                    case "external_write": File.WriteAllText(Path.Combine(user, a[1].Replace('/', '\\')), a[2]); break;
                    case "rescan":
                        nitFormRef.GetType().GetProperty("ValidateOnActivate", All)?.SetValue(nitFormRef, true);
                        var f = nitFormRef.GetType().GetField("ValidateOnActivate", All); if (f != null) f.SetValue(nitFormRef, true);
                        CallForm("ActivatedEventProcessing");
                        break;
                    default: Log("unknown op " + op); break;
                }
            }
            catch (Exception e) { var x = e is TargetInvocationException && e.InnerException != null ? e.InnerException : e; Log("STEP FAILED: " + x); snaps.WriteLine(step + "\terror\t" + x.GetType().Name + "\t" + x.Message.Replace('\t', ' ').Replace('\n', ' ')); }
            Settle();
            Snapshot(step);
        }
        snaps.Close();
        return n + " steps";
    }

    // Let NIT finish its background work (CRC workers, file monitor) the way an idle
    // app would before the user's next click; back-to-back steps otherwise hit
    // Windows sharing violations on files NIT is still reading.
    static void Settle()
    {
        var until = DateTime.Now.AddSeconds(3);
        while (DateTime.Now < until) { Application.DoEvents(); Thread.Sleep(50); }
    }

    static void Snapshot(string step)
    {
        Action<string, string, string> W = (k, key, v) => snaps.WriteLine(step + "\t" + k + "\t" + key + "\t" + (v ?? "").Replace('\t', ' ').Replace('\r', ' ').Replace('\n', ' '));
        foreach (var root in new[] { new { K = "game", P = Sb + @"\user" }, new { K = "lib", P = Sb + @"\eelib" } })
            foreach (var f in Directory.GetFiles(root.P, "*", SearchOption.AllDirectories).OrderBy(x => x, StringComparer.OrdinalIgnoreCase))
            {
                var rel = f.Substring(root.P.Length + 1).Replace('\\', '/');
                var fi = new FileInfo(f);
                W(root.K, rel, fi.Length < 200 ? File.ReadAllText(f) : "len=" + fi.Length);
            }
        string mods = (string)Member(T("Paths"), "ProfileMods");
        foreach (var f in Directory.GetFiles(mods, "*", SearchOption.AllDirectories).OrderBy(x => x, StringComparer.OrdinalIgnoreCase))
        {
            var rel = f.Substring(mods.Length + 1).Replace('\\', '/');
            var fi = new FileInfo(f);
            W("store", rel, fi.Length < 200 && !rel.EndsWith(".rtf") ? File.ReadAllText(f) : "len=" + fi.Length);
        }
        var pd = Pd();
        var modList = (System.Collections.IDictionary)Member(pd, "ModList");
        foreach (System.Collections.DictionaryEntry de in modList)
        {
            var md = de.Value; var t = md.GetType();
            if ((bool)t.GetProperty("IsGroupItem", All).GetValue(md)) continue;
            var deps = ((IEnumerable<string>)t.GetProperty("Dependencies", All).GetValue(md)).OrderBy(x => x);
            W("mod", Convert.ToString(de.Key), "group=" + t.GetProperty("Group", All).GetValue(md) + ";installed=" + t.GetProperty("Installed", All).GetValue(md)
                + ";installState=" + t.GetProperty("InstallState", All).GetValue(md) + ";modState=" + t.GetProperty("ModState", All).GetValue(md)
                + ";deps=" + string.Join(",", deps));
        }
        var fileList = (System.Collections.IDictionary)Member(pd, "FileList");
        foreach (System.Collections.DictionaryEntry de in fileList)
        {
            var k = de.Key; string full = Convert.ToString(k.GetType().GetProperty("FullKey", All).GetValue(k));
            W("filedata", full, Describe(de.Value));
        }
        var info = Member(T("Defs"), "ui");
        if (info != null) { try { var inf = info.GetType().GetProperty("Info", All).GetValue(info); W("status", "info", Convert.ToString(inf.GetType().GetProperty("Text", All).GetValue(inf))); } catch { } }
        snaps.Flush();
    }

    static IButtonControl FindButton(Control c, string text)
    {
        foreach (Control k in c.Controls)
        {
            if (k is IButtonControl && k.Text.Replace("&", "") == text) return (IButtonControl)k;
            var sub = FindButton(k, text); if (sub != null) return sub;
        }
        return null;
    }

    static TextBox FindText(Control c)
    {
        foreach (Control k in c.Controls)
        {
            if (k is TextBox && k.Visible && !((TextBox)k).ReadOnly) return (TextBox)k;
            var sub = FindText(k); if (sub != null) return sub;
        }
        return null;
    }

    static RadioButton FindRadio(Control c, string prefix)
    {
        foreach (Control k in c.Controls)
        {
            if (k is RadioButton && k.Text.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)) return (RadioButton)k;
            var sub = FindRadio(k, prefix); if (sub != null) return sub;
        }
        return null;
    }

    static void RunQueries()
    {
        string inFile = Path.Combine(Root, "in.tsv");
        if (!File.Exists(inFile)) { Log("no in.tsv"); return; }
        var defs = T("Defs");
        var map = defs.GetField("Map", All)?.GetValue(null) ?? T("NIT").GetField("Map", All)?.GetValue(null);
        using (var o = new StreamWriter(Path.Combine(Root, "out.tsv"), false))
        {
            foreach (var line in File.ReadLines(inFile))
            {
                var p = line.Split(new[] { '\t' }); string cmd = p[0], arg = p.Length > 1 ? p[1] : "";
                string r;
                try { r = Query(map, cmd, arg); }
                catch (Exception e) { var x = e is TargetInvocationException && e.InnerException != null ? e.InnerException : e; Log("query '" + cmd + "' failed: " + x); r = "EXC:" + x.GetType().Name + ":" + x.Message.Replace('\t', ' ').Replace('\n', ' '); }
                o.WriteLine(cmd + "\t" + arg + "\t" + r);
            }
        }
    }

    static object DownloadForm;

    // Drive NIT's real Download Project form: set the URL, run RetrieveProject, and read
    // the two lists it fills (LvProject = the project's offered files, LvRequirements =
    // prerequisite projects and their offered files), plus the mod folder and group.
    static string VaultSelect(string url)
    {
        var dpT = T("DownloadProject");
        if (DownloadForm == null)
        {
            DownloadForm = Activator.CreateInstance(dpT);
            ((Form)DownloadForm).Show();
            var until = DateTime.Now.AddSeconds(3);
            while (DateTime.Now < until) { Application.DoEvents(); Thread.Sleep(50); }
        }
        var form = (Form)DownloadForm;
        // VB WithEvents controls are properties over a "_Name" field; plain fields otherwise.
        Func<string, object> field = n =>
        {
            var pr = dpT.GetProperty(n, All);
            if (pr != null) return pr.GetValue(form);
            var f = dpT.GetField(n, All) ?? dpT.GetField("_" + n, All);
            return f.GetValue(form);
        };
        ((TextBox)field("TxUrl")).Text = url;
        var retrieve = dpT.GetMethod("RetrieveProject", All);
        var ok = (bool)retrieve.Invoke(form, new object[] { Type.Missing });
        var lines = new List<string>();
        Action<string, string> w = (k, v) => lines.Add(url + "\t" + k + "\t" + v);
        w("ok", ok.ToString());
        var scraper = field("Scraper");
        if (scraper != null) w("title", Convert.ToString(scraper.GetType().GetProperty("ProjectTitle").GetValue(scraper)));
        w("mod_folder", ((Control)field("TxModName")).Text);
        var mb = field("MbGroup");
        w("group", Convert.ToString(mb.GetType().GetProperty("DisplayMember").GetValue(mb)));
        foreach (ListViewItem item in ((ListView)field("LvProject")).Items)
        {
            if (item.Tag == null) { w("file", "(none)"); continue; }
            w("file", Convert.ToString(item.Tag.GetType().GetProperty("Filename").GetValue(item.Tag)));
        }
        foreach (ListViewItem item in ((ListView)field("LvRequirements")).Items)
        {
            if (item.Tag == null) { w("req", "(none)"); continue; }
            var t = item.Tag.GetType();
            var project = Convert.ToString(t.GetProperty("ProjectTitle").GetValue(item.Tag));
            var file = Convert.ToString(t.GetProperty("Filename").GetValue(item.Tag));
            w("req", project + " | " + file + " | " + item.Text);
        }
        File.AppendAllLines(Path.Combine(Root, "select.tsv"), lines);
        return ok + " " + lines.Count;
    }

    // Render one of NIT's forms the way it opens (Load runs, NIT's own main window is
    // loaded behind it) and write its image plus its control tree (type, name, caption,
    // bounds, toolstrip items) for structural comparison with Vaultkeeper's screen.
    // A form built without showing it: the parameterless constructor, else the one
    // with the fewest parameters given neutral defaults (null, 0, false, "").
    static int DialogsAnswered;

    static Form BuildForm(Type t)
    {
        var ctor = t.GetConstructor(Type.EmptyTypes);
        if (ctor != null) return (Form)ctor.Invoke(null);
        var best = t.GetConstructors().OrderBy(c => c.GetParameters().Length).FirstOrDefault();
        if (best == null) return null;
        var args = best.GetParameters().Select(p => Neutral(p.ParameterType.IsByRef
            ? p.ParameterType.GetElementType() : p.ParameterType)).ToArray();
        return (Form)best.Invoke(args);
    }

    // "", 0/false, an empty collection (anything with a parameterless constructor), else null.
    static object Neutral(Type t)
    {
        if (t == typeof(string)) return "";
        // A path list (GameSavesPathDialogue): an empty one makes NIT terminate.
        if (t == typeof(List<string>)) return new List<string> { Path.Combine(Root, "sb", "user", "saves") };
        if (t.IsValueType) return Activator.CreateInstance(t);
        if (t.GetConstructor(Type.EmptyTypes) != null && !typeof(Control).IsAssignableFrom(t))
            try { return Activator.CreateInstance(t); } catch { }
        return null;
    }

    static List<string> Structure(Form form, string note)
    {
        var lines = new List<string> { "FORM\t" + form.Text + "\t" + form.Width + "x" + form.Height + note };
        DumpControls(form, 0, lines);
        return lines;
    }

    static bool SaveBitmap(Form form, string path)
    {
        try
        {
            var bmp = new System.Drawing.Bitmap(Math.Max(1, form.Width), Math.Max(1, form.Height));
            form.DrawToBitmap(bmp, new System.Drawing.Rectangle(0, 0, bmp.Width, bmp.Height));
            bmp.Save(path, System.Drawing.Imaging.ImageFormat.Png);
            return true;
        }
        catch { return false; }
    }

    static string Screenshot(string name)
    {
        string dir = Path.Combine(Root, "shots"); Directory.CreateDirectory(dir);
        string png = Path.Combine(dir, name + ".png"), txt = Path.Combine(dir, name + ".controls.txt");
        if (name == "NIT")
        {
            var main = (Form)nitFormRef;
            SaveBitmap(main, png);
            var all = Structure(main, "");
            File.WriteAllLines(txt, all);
            return all.Count + " lines";
        }
        var t = T(name);
        if (t == null) return "NO-TYPE";
        Form form = BuildForm(t);
        if (form == null) return "NO-CTOR";
        // The designer's structure, before Load can close the form (several close
        // themselves when the sandbox has nothing for them to act on).
        var designed = Structure(form, "\t(before Load)");
        string how;
        int dialogsBefore = DialogsAnswered;
        try
        {
            form.StartPosition = FormStartPosition.Manual;
            form.Location = new System.Drawing.Point(20, 20);
            form.Show((Form)nitFormRef);
            var until = DateTime.Now.AddSeconds(2.5);
            while (DateTime.Now < until && !form.IsDisposed) { Application.DoEvents(); Thread.Sleep(50); }
            if (form.IsDisposed) throw new ObjectDisposedException(name);
            SaveBitmap(form, png);
            var shown = Structure(form, "");
            File.WriteAllLines(txt, shown);
            how = shown.Count + " lines";
        }
        catch (Exception ex)
        {
            if (ex is TargetInvocationException && ex.InnerException != null) ex = ex.InnerException;
            File.WriteAllLines(txt, designed);
            // Draw a second copy that is never shown (no Load for it to close in),
            // unless Load put up a prompt: drawing can run Load again, and that
            // prompt, owned by an invisible form, is never answered.
            bool drawn = false, prompted = DialogsAnswered != dialogsBefore;
            if (!prompted)
                try { var copy = BuildForm(t); drawn = SaveBitmap(copy, png); copy.Dispose(); } catch { }
            how = designed.Count + " lines (before Load; " + ex.GetType().Name
                + (drawn ? "; unshown render" : prompted ? "; prompted on Load, no render" : "; no render") + ")";
        }
        try { if (!form.IsDisposed) { form.Close(); form.Dispose(); } } catch { }
        return how;
    }

    static void DumpControls(Control c, int depth, List<string> lines)
    {
        foreach (Control k in c.Controls)
        {
            string pad = new string(' ', depth * 2);
            lines.Add(pad + k.GetType().Name + "\t" + k.Name + "\t" + (k.Text ?? "").Replace("\r", " ").Replace("\n", " ")
                + "\t" + k.Bounds.X + "," + k.Bounds.Y + "," + k.Bounds.Width + "," + k.Bounds.Height + (k.Visible ? "" : "\thidden"));
            var ts = k as ToolStrip;
            if (ts != null) foreach (ToolStripItem item in ts.Items) DumpItem(item, depth + 1, lines);
            var lv = k as ListView;
            if (lv != null) foreach (ColumnHeader col in lv.Columns) lines.Add(pad + "  Column\t" + col.Text + "\t" + col.Width);
            DumpControls(k, depth + 1, lines);
        }
    }

    static void DumpItem(ToolStripItem item, int depth, List<string> lines)
    {
        string pad = new string(' ', depth * 2);
        lines.Add(pad + item.GetType().Name + "\t" + item.Name + "\t" + (item.Text ?? "").Replace("&", "")
            + "\t" + (item.Image != null ? "img" : "") + (item.Available ? "" : "\thidden") + "\t" + (item.ToolTipText ?? ""));
        var dd = item as ToolStripDropDownItem;
        if (dd != null) foreach (ToolStripItem sub in dd.DropDownItems) DumpItem(sub, depth + 1, lines);
    }

    static string Query(object map, string cmd, string arg)
    {
        switch (cmd)
        {
            case "map":        // target folder for a source file path
                return (string)map.GetType().GetMethod("GetMappedFolder", new[] { typeof(FileInfo), typeof(bool) }).Invoke(map, new object[] { new FileInfo(arg), false });
            case "dump-tables":  // every dictionary-valued member of the live Mapper, one entry per line
            {
                var lines = new List<string>();
                foreach (var f in map.GetType().GetFields(All))
                {
                    var v = f.IsStatic ? f.GetValue(null) : f.GetValue(map);
                    var d = v as System.Collections.IDictionary; if (d == null) continue;
                    foreach (System.Collections.DictionaryEntry de in d)
                    {
                        string val = de.Value is string || !(de.Value is System.Collections.IEnumerable) ? Convert.ToString(de.Value)
                            : string.Join("|", ((System.Collections.IEnumerable)de.Value).Cast<object>().Select(Convert.ToString));
                        lines.Add(f.Name + "=" + de.Key + "=" + val);
                    }
                }
                File.WriteAllLines(Path.Combine(Root, "tables.txt"), lines);
                return lines.Count + " entries";
            }
            case "rules-dump":  // every parsed Project (all public properties, recursively) -> rules.txt
            {
                var rulesT = T("VaultDownloadRules");
                var rules = Activator.CreateInstance(rulesT, new object[] { "" });
                var lines = new List<string>();
                var projects = (System.Collections.IDictionary)rulesT.GetProperty("Projects", All).GetValue(rules);
                foreach (System.Collections.DictionaryEntry de in projects)
                    Flatten(Convert.ToString(de.Key), "", de.Value, lines, 0);
                var excl = (System.Collections.IDictionary)rulesT.GetField("ExcludeFiles", All).GetValue(rules);
                foreach (System.Collections.DictionaryEntry de in excl)
                    lines.Add(de.Key + "\tExcludes\t" + string.Join("|", ((System.Collections.IEnumerable)de.Value).Cast<object>().Select(Convert.ToString).OrderBy(x => x, StringComparer.OrdinalIgnoreCase)));
                File.WriteAllLines(Path.Combine(Root, "rules.txt"), lines);
                return projects.Count + " projects, " + lines.Count + " lines";
            }
            case "modname":     // NIT.Paste ModPasteInfo(group, sourceName).ModName
            {
                var mpi = T("NIT").GetNestedType("ModPasteInfo", All);
                var o = Activator.CreateInstance(mpi, All, null, new object[] { "Group", arg }, null);
                return Convert.ToString(mpi.GetProperty("ModName", All).GetValue(o));
            }
            case "scenario":    // run a stage-2 scenario script; snapshots -> C:\nitdiff\snaps.tsv
                return RunScenario(arg);
            case "vault-select":  // DownloadProject for a URL: offered files + prerequisites -> select.tsv
                return VaultSelect(arg);
            case "screenshot":  // screen parity: render a form -> C:\nitdiff\shots\<Form>.png + .controls.txt
                return Screenshot(arg);
            case "wincompare":  // LazWorks WinCompare(x, y) — NIT's sort for priorities; arg "x|y"
            {
                var parts = arg.Split(new[] { '|' });
                var misc = AppDomain.CurrentDomain.GetAssemblies().SelectMany(asm => { try { return asm.GetTypes(); } catch (ReflectionTypeLoadException x) { return x.Types.Where(t => t != null).ToArray(); } })
                    .First(t => t.GetMethod("WinCompare", BindingFlags.Public | BindingFlags.Static, null, new[] { typeof(string), typeof(string) }, null) != null);
                var r = (int)misc.GetMethod("WinCompare", new[] { typeof(string), typeof(string) }).Invoke(null, new object[] { parts[0], parts[1] });
                return Math.Sign(r).ToString();
            }
            case "excl-fi":    // IsExcludedFile(FileInfo): checks "name" and "parent\name"
                return Convert.ToString(map.GetType().GetMethod("IsExcludedFile", new[] { typeof(FileInfo) }).Invoke(map, new object[] { new FileInfo(arg) }));
            case "map-erf":
                return (string)map.GetType().GetMethod("GetMappedFolder", new[] { typeof(FileInfo), typeof(bool) }).Invoke(map, new object[] { new FileInfo(arg), true });
            default:
                // Generic: "Mapper.Method" with one string argument, e.g. Mapper.IsExcludedFile
                var dot = cmd.IndexOf('.');
                if (dot > 0 && cmd.Substring(0, dot) == "Mapper")
                {
                    var m = map.GetType().GetMethods(All).First(x => x.Name == cmd.Substring(dot + 1) && x.GetParameters().Length == 1 && x.GetParameters()[0].ParameterType == typeof(string));
                    return Convert.ToString(m.Invoke(map, new object[] { arg }));
                }
                return "UNKNOWN-COMMAND";
        }
    }
}
