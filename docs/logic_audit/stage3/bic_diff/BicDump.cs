using System; using System.IO; using System.Linq; using System.Reflection; using System.Collections;
class D { static void Main(string[] args) {
  var a = Assembly.LoadFrom("BicFileReader.dll");
  var t = a.GetType("BicFileReader.Info");
  foreach (var f in Directory.GetFiles(args[0], "*.bic").OrderBy(x => x)) {
    var info = Activator.CreateInstance(t);
    string err;
    try { err = (string)t.GetMethod("GetInfo").Invoke(info, new object[]{f}); }
    catch (Exception e) { err = "EXC " + (e.InnerException ?? e).Message; }
    var name = Path.GetFileName(f);
    if (!string.IsNullOrEmpty(err)) { Console.WriteLine(name + "\terror\t" + err); continue; }
    foreach (var p in t.GetProperties().OrderBy(p => p.Name)) {
      var v = p.GetValue(info);
      string s;
      if (v is IDictionary d) {
        var parts = new System.Collections.Generic.List<string>();
        foreach (DictionaryEntry e in d) parts.Add(e.Key + ":" + e.Value);
        s = string.Join(",", parts);
      } else s = v == null ? "" : v.ToString();
      Console.WriteLine(name + "\t" + p.Name + "\t" + s);
    }
  } } }
