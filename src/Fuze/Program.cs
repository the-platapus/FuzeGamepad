using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading;
using System.Runtime.InteropServices;
using HidLibrary;
using ScpDriverInterface;

namespace Fuze
{
    class Program
    {
        private static ScpBus global_scpBus;

        static bool ConsoleEventCallback(int eventType)
        {
            if (eventType == 2)
                global_scpBus.UnplugAll();

            return false;
        }

        static ConsoleEventDelegate handler;

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
                    Log.WriteLine(e.Message, Log.LogType.exception);
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

            // ============================
            // TRY OLD METHOD (USB FIRST)
            // ============================
            var usbDevices = HidDevices.Enumerate();

            HidDevice Device = null;

            //if (usbDevices.Count > 0)
            //{
            //Device = usbDevices.First();
            //Log.WriteLine("USB controller auto-detected.");
            //}
            //else
            {
                // ============================
                // FALLBACK → MANUAL SELECTION
                // ============================
                var devices = HidDevices.Enumerate().ToList();
                var candidates = devices
                        .Where(d => d.Capabilities.InputReportByteLength >= 10)
                        .ToList();

                if (candidates.Count == 0)
                {
                    Log.WriteLine("\nNo valid input-capable HID devices found.", Log.LogType.error);
                    return;
                }
                Console.Write("\n==> No Fuze Game Controller found in USB Devices. Select controller if in Bluetooth mode, if not then restart the service.\n");

                for (int i = 0; i < candidates.Count; i++)
                {
                    var d = candidates[i];

                    byte[] productBytes;
                    d.ReadProduct(out productBytes);

                    string name = productBytes != null
                        ? Encoding.ASCII.GetString(productBytes).Trim('\0')
                        : "Unknown";

                    Console.WriteLine($"{i}: {name}");
                    //Console.WriteLine($"    Path: {d.DevicePath}");
                    Console.WriteLine($"Input: {d.Capabilities.InputReportByteLength}");
                    Console.WriteLine($"Output: {d.Capabilities.OutputReportByteLength}");
                    Console.WriteLine($"Feature: {d.Capabilities.FeatureReportByteLength}");
            }

            int selected = -1;

                while (true)
                {
                    Console.Write("\nSelect controller index: ");
                    string input = Console.ReadLine();

                    if (int.TryParse(input, out selected) &&
                        selected >= 0 &&
                        selected < candidates.Count)
                        break;

                    Console.WriteLine("Invalid selection. Try again.");
                }

                Device = candidates[selected];
            }
            // ============================
            // OPEN DEVICE (BT + USB SAFE)
            // ============================
            try
            {
                Device.OpenDevice(
                    DeviceMode.Overlapped,
                    DeviceMode.Overlapped,
                    ShareMode.ShareRead | ShareMode.ShareWrite
                );

                Log.WriteLine("Opened device in shared mode.");
            }
            catch (Exception ex)
            {
                Log.WriteLine("Failed to open device: " + ex.Message, Log.LogType.warning);
                return;
            }

            // ============================
            // READ INFO
            // ============================
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

            Log.WriteLine($"Selected Device: {productName} | Serial: {serial}");

            // ============================
            // START GAMEPAD PIPELINE
            // ============================
            FuzeGamepad gamepad = new FuzeGamepad(Device, scpBus, 1);

            Log.WriteLine("Controller connected");

            while (true)
                Thread.Sleep(1000);
        }
    }
}