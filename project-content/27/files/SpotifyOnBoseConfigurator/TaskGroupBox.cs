using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace SpotifyOnBoseConfigurator
{
    class TaskGroupBox(Microsoft.Win32.TaskScheduler.Task task) : System.Windows.Forms.GroupBox()
    {
        public readonly Microsoft.Win32.TaskScheduler.Task task = task;
    }
}
