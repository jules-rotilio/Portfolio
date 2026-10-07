namespace ShowMicVolume
{
    public class VerticalNoAnimationProgressBar : ProgressBar
    {
        public VerticalNoAnimationProgressBar()
        {
            this.SetStyle(ControlStyles.UserPaint, true);
        }

        protected override CreateParams CreateParams
        {
            get
            {
                CreateParams cp = base.CreateParams;
                cp.Style |= 0x04; // Set the progress bar to vertical
                return cp;
            }
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            Rectangle rect = ClientRectangle;
            if (ProgressBarRenderer.IsSupported)
                ProgressBarRenderer.DrawVerticalBar(e.Graphics, rect);
            rect.Height = (int)(rect.Height * ((double)Value / Maximum));
            rect.Y = ClientRectangle.Height - rect.Height; // Start from bottom
            e.Graphics.FillRectangle(Brushes.LimeGreen, rect);
        }
    }
}