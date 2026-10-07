using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace Cascade
{
    public class RssItem
    {
        public string? GUID;

        public string? Title;
        public string? Description;
        public string? Link;
        public DateTimeOffset PublishDate = new();

        public RssItem() { }

        public void Log()
        {
            var sb = new StringBuilder();
            sb.AppendLine($"GUID : {GUID}");
            sb.AppendLine($"Title : {Title}");
            sb.AppendLine($"Description : {Description}");
            sb.AppendLine($"Link : {Link}");
            Console.WriteLine(sb);
        }
    }
}
