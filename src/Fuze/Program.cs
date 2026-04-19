using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using HidLibrary;
using ScpDriverInterface;
using System.Threading;
using System.Runtime.InteropServices;

namespace Fuze
{
    class Program
    {
        private static ScpBus global_scpBus;
        static bool ConsoleEventCallback(int eventType)
        {
            if (eventType == 2)
            {
                global_scpBus.UnplugAll();
            }
            return false;
        }
        static ConsoleEventDelegate handler;   // Keeps it from getting garbage collected
                                               // Pinvoke
        private delegate bool ConsoleEventDelegate(int eventType);
        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool SetConsoleCtrlHandler(ConsoleEventDelegate callback, bool add);



        public static string ByteArrayToHexString(byte[] bytes)
        {
            return string.Join(string.Empty, Array.ConvertAll(bytes, b => b.ToString("X2")));
        }



        static void Main(string[] args)
        {
            while (true)
            {
                try
                {
                    Init();
                }
                catch (Exception e)
                {
                    Log.WriteLine(e.Message,Log.LogType.exception);
                }

                Log.WriteLine("An exception occurred. Press ENTER to retry, or Alt+F4 to exit.");
                Console.ReadLine();

            }
        }

        private static void Init()
        {
            ScpBus scpBus = new ScpBus();
            scpBus.UnplugAll();
            global_scpBus = scpBus;

            handler = new ConsoleEventDelegate(ConsoleEventCallback);
            SetConsoleCtrlHandler(handler, true);

            var compatibleDevices = HidDevices.Enumerate(0x79, 0x181c).ToList();
            Thread.Sleep(400);

            FuzeGamepad[] gamepads = new FuzeGamepad[4];
            int index = 1;
            //compatibleDevices.RemoveRange(1, compatibleDevices.Count - 1);
            foreach (var deviceInstance in compatibleDevices)
            {
                HidDevice Device = deviceInstance;

                bool opened = false;

                try
                {
                    Device.OpenDevice(DeviceMode.Overlapped, DeviceMode.Overlapped,
                        ShareMode.ShareRead | ShareMode.ShareWrite);

                    Log.WriteLine("Opened device in shared mode.");
                    opened = true;
                }
                catch (Exception ex)
                {
                    Log.WriteLine("Failed to open device: " + ex.Message, Log.LogType.warning);
                    continue;
                }

                if (!opened)
                    continue;

                byte[] serialNumber;
                byte[] product;

                Device.ReadSerialNumber(out serialNumber);
                Device.ReadProduct(out product);

                string serial = serialNumber != null
                    ? Encoding.ASCII.GetString(serialNumber).Trim('\0')
                    : "unknown";

                string productName = product != null
                    ? Encoding.ASCII.GetString(product).Trim('\0')
                    : "unknown";

                Log.WriteLine($"Device: {productName} | Serial: {serial}");

                gamepads[index - 1] = new FuzeGamepad(Device, scpBus, index);
                index++;

                if (index >= 5)
                    break;
            }
            Log.WriteLine(string.Format("{0} controllers connected", index - 1));

            while (true)
            {
                Thread.Sleep(1000);
            }
        }
    }
}
