using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace SpotifyOnBoseConfigurator
{
    public partial class PlaylistNotFound: Form
    {
        public event Action<string> ValiderClicked;

        public PlaylistNotFound()
        {
            InitializeComponent();
            validerButton.Click += (s, e) =>
            {
                string playlistName = playlistNameTextBox.Text;
                ValiderClicked?.Invoke(playlistName);
                this.Close();
            };
            annulerButton.Click += (s, e) =>
            {
                ValiderClicked?.Invoke(string.Empty);
                this.Close();
            };
        }
    }
}
