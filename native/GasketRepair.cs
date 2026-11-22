using System;
using System.IO;
using System.Threading.Tasks;
using Windows.Storage;
using Windows.Storage.Streams;
using Windows.Graphics.Printing3D;
class GasketRepair {
 [MTAThread] static int Main(string[] args) {
  if(args.Length != 2) { Console.Error.WriteLine("Expected input and output 3MF paths"); return 2; }
  try { Run(args); return 0; }
  catch(Exception e) { Console.Error.WriteLine(e.ToString()); return 1; }
 }
 static T Wait<T>(Windows.Foundation.IAsyncOperation<T> op) { return System.WindowsRuntimeSystemExtensions.AsTask<T>(op).GetAwaiter().GetResult(); }
 static void Run(string[] args) {
  using(var input=new InMemoryRandomAccessStream()) {
   using(var source=File.OpenRead(args[0])) {
    var sink=input.AsStreamForWrite(); source.CopyTo(sink); sink.Flush();
   }
   input.Seek(0);
   var package=new Printing3D3MFPackage();
   var model=Wait<Printing3DModel>(package.LoadModelFromPackageAsync(input));
   Console.WriteLine("Loaded local mesh");
   bool ok=Wait<bool>(model.TryPartialRepairAsync(TimeSpan.FromSeconds(60)));
   Console.WriteLine("Repair completed: "+ok);
   if(!ok) throw new InvalidOperationException("Local repair did not complete");
   System.WindowsRuntimeSystemExtensions.AsTask(package.SaveModelToPackageAsync(model)).GetAwaiter().GetResult();
   using(var output=Wait<IRandomAccessStream>(package.SaveAsync()))
   using(var reader=output.AsStreamForRead())
   using(var destination=File.Create(args[1])) reader.CopyTo(destination);
  }
 }
}
