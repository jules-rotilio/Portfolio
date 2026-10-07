using System;
using System.Diagnostics;
using System.Drawing;
using System.Windows.Forms;
using CefSharp;
using CefSharp.WinForms;

namespace GoogleMessages
{
    internal static class Program
    {

        [STAThread]
        static void Main()
        {
            ApplicationConfiguration.Initialize();
            Form form = new();
            form.Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
            var settings = new CefSettings
            {
                UserAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.92 Safari/537.36 /CefSharp Browser" + Cef.CefSharpVersion,
                CachePath = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData) + @"\CEF"
            };
            settings.CefCommandLineArgs.Add("force-dark-mode");
            Cef.Initialize(settings);

            var browser = new ChromiumWebBrowser("https://messages.google.com/web");
            form.Controls.Add(browser);
            browser.Dock = DockStyle.Fill;

            form.Width = 1500;
            form.Height = 1080;
            form.WindowState = FormWindowState.Maximized;
            form.BackColor = Color.Black;
            form.ForeColor = Color.Black;

            _ = new TrayIconApp(form);
            Application.Run(form);
        }
    }

    public class TrayIconApp
    {
        private readonly NotifyIcon TrayIcon;
        private readonly Form form;

        public TrayIconApp(Form form)
        {
            this.form = form;
            TrayIcon = new NotifyIcon()
            {
                Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath),
                ContextMenuStrip = new ContextMenuStrip(),
                Visible = true
            };

            TrayIcon.ContextMenuStrip.Items.Add("Exit", null, Exit);
            TrayIcon.ContextMenuStrip.Items.Add("Hide", null, ToggleVisibility);
            //trayicon onclick

            TrayIcon.MouseClick += ToggleVisibility;

        }

        void Exit(object sender, EventArgs e)
        {
            TrayIcon.Visible = false;
            TrayIcon.Dispose();
            Application.Exit();
        }

        void ToggleVisibility(object sender, MouseEventArgs e)
        {
            if (e.Button == MouseButtons.Left)
            {
                if (form.Visible)
                {
                    TrayIcon.ContextMenuStrip.Items[1].Text = "Show";
                }
                else
                {
                    TrayIcon.ContextMenuStrip.Items[1].Text = "Hide";
                }
                form.Visible = !form.Visible;
            }

        }
        void ToggleVisibility(object sender, EventArgs e)
        {
            if (form.Visible)
            {
                TrayIcon.ContextMenuStrip.Items[1].Text = "Show";
            }
            else
            {
                TrayIcon.ContextMenuStrip.Items[1].Text = "Hide";
            }
            form.Visible = !form.Visible;
        }
    }
}
