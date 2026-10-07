using System;
using System.Drawing;
using System.Windows.Forms;

namespace PongGame
{
    public partial class PongForm : Form
    {
        private int ballXSpeed = 3;
        private int ballYSpeed = 3;
        private int playerSpeed = 8;

        public PongForm()
        {
            InitializeComponent();
            timer1.Interval = 5;
            timer1.Tick += new EventHandler(Update);
            timer1.Start();
        }

        private void Update(object sender, EventArgs e)
        {
            // Move the ball
            ball.Left += ballXSpeed;
            ball.Top += ballYSpeed;

            // Bounce the ball off the top and bottom walls
            if (ball.Top <= 0 || ball.Bottom >= ClientSize.Height)
            {
                ballYSpeed = -ballYSpeed;
            }

            // Bounce the ball off the paddles
            if (ball.Bounds.IntersectsWith(player1.Bounds) || ball.Bounds.IntersectsWith(player2.Bounds))
            {
                ballXSpeed = -ballXSpeed;
            }

            // Move the paddles
            if (wKeyPressed && player1.Top > 0)
            {
                player1.Top -= playerSpeed;
            }
            if (sKeyPressed && player1.Bottom < ClientSize.Height)
            {
                player1.Top += playerSpeed;
            }
            if (upArrowPressed && player2.Top > 0)
            {
                player2.Top -= playerSpeed;
            }
            if (downArrowPressed && player2.Bottom < ClientSize.Height)
            {
                player2.Top += playerSpeed;
            }

            // Check for scoring
            if (ball.Left <= 0)
            {
                // Player 2 scores
                ball.Left = ClientSize.Width / 2;
                ballXSpeed = -ballXSpeed;
            }
            if (ball.Right >= ClientSize.Width)
            {
                // Player 1 scores
                ball.Left = ClientSize.Width / 2;
                ballXSpeed = -ballXSpeed;
            }
        }

        private bool upArrowPressed = false;
        private bool downArrowPressed = false;
        private bool wKeyPressed = false;
        private bool sKeyPressed = false;

        private void PongForm_KeyDown(object sender, KeyEventArgs e)
        {
            if (e.KeyCode == Keys.Up)
            {
                upArrowPressed = true;
            }
            if (e.KeyCode == Keys.Down)
            {
                downArrowPressed = true;
            }
            if (e.KeyCode == Keys.W)
            {
                wKeyPressed = true;
            }
            if (e.KeyCode == Keys.S)
            {
                sKeyPressed = true;
            }
        }

        private void PongForm_KeyUp(object sender, KeyEventArgs e)
        {
            if (e.KeyCode == Keys.Up)
            {
                upArrowPressed = false;
            }
            if (e.KeyCode == Keys.Down)
            {
                downArrowPressed = false;
            }
            if (e.KeyCode == Keys.W)
            {
                wKeyPressed = false;
            }
            if (e.KeyCode == Keys.S)
            {
                sKeyPressed = false;
            }
        }
    }
}
