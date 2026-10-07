using System;
using System.Text;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Data;
using System.Windows.Documents;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Navigation;
using System.Windows.Shapes;

namespace SudokuSolverGUI
{
    /// <summary>
    /// Interaction logic for MainWindow.xaml
    /// </summary>
    public partial class MainWindow : Window
    {
        private int[,] sudokuBoard;
        private readonly TextBox[,] sudokuGridBoxes;
        private readonly Random rand = new();

        public MainWindow()
        {
            InitializeComponent();
            Title = Properties.Resources.ResourceManager.GetString("SudokuSolver");
            SolveButton.Content = Properties.Resources.ResourceManager.GetString("Solve");
            GenerateButton.Content = Properties.Resources.ResourceManager.GetString("Generate");
            CheckButton.Content = Properties.Resources.ResourceManager.GetString("Check");
            ClearButton.Content = Properties.Resources.ResourceManager.GetString("Clear");
            sudokuBoard = new int[9, 9];
            sudokuGridBoxes = new TextBox[9, 9];
            GenerateSudokuGrid(firstGeneration:true);
        }

        private int[,] GenerateBoard()
        {
            int[,] board = new int[9, 9];
            int[] numbers = [1, 2, 3, 4, 5, 6, 7, 8, 9];

            // Shuffle numbers and fill the diagonal boxes to ensure a unique solution
            for (int i = 0; i < 3; i++)
            {
                Shuffle(numbers);
                FillDiagonalBox(board, i * 3, numbers);
            }

            // Solve the partially filled board to get a full solution
            SolveSudoku(board);

            // Remove numbers to create the puzzle
            int numbersToRemove = 40; // You can adjust the difficulty by changing this number
            while (numbersToRemove > 0)
            {
                int row = rand.Next(9);
                int col = rand.Next(9);

                if (board[row, col] != 0)
                {
                    board[row, col] = 0;
                    numbersToRemove--;
                }
            }

            return board;
        }

        private static bool SolveSudoku(int[,] board)
        {
            for (int row = 0; row < board.GetLength(0); row++)
            {
                for (int col = 0; col < board.GetLength(1); col++)
                {
                    if (board[row, col] == 0)
                    {
                        for (int number = 1; number <= 9; number++)
                        {
                            if (IsValid(board, row, col, number))
                            {
                                board[row, col] = number;

                                if (SolveSudoku(board))
                                {
                                    return true;
                                }

                                board[row, col] = 0;
                            }
                        }
                        return false; // return false as soon as an empty cell is found
                    }
                }
            }
            return true;
        }

        private static bool IsValid(int[,] board, int row, int col, int number)
        {
            int startRow = row - row % 3;
            int startCol = col - col % 3;

            for (int i = 0; i < 9; i++)
            {
                if (board[row, i] == number || board[i, col] == number)
                {
                    return false; // return false as soon as a match is found
                }
            }

            for (int i = 0; i < 3; i++)
            {
                for (int j = 0; j < 3; j++)
                {
                    if (board[i + startRow, j + startCol] == number)
                    {
                        return false; // return false as soon as a match is found
                    }
                }
            }

            return true;
        }

        private void Shuffle(int[] array)
        {
            for (int i = array.Length - 1; i > 0; i--)
            {
                int j = rand.Next(i + 1);
                (array[j], array[i]) = (array[i], array[j]);
            }
        }

        private static void FillDiagonalBox(int[,] board, int start, int[] numbers)
        {
            for (int i = 0; i < 3; i++)
            {
                for (int j = 0; j < 3; j++)
                {
                    board[start + i, start + j] = numbers[i * 3 + j];
                }
            }
        }

        private void GenerateSudokuGrid(bool firstGeneration = false)
        {
            if (!firstGeneration)
            {
                sudokuBoard = GenerateBoard();
            }
            for (int i = 0; i < 9; i++)
            {
                for (int j = 0; j < 9; j++)
                {
                    sudokuGridBoxes[i, j] = new TextBox
                    {
                        Text = sudokuBoard[i, j] == 0 ? string.Empty : sudokuBoard[i, j].ToString(),
                        Width = 60,
                        Height = 60,
                        Margin = new Thickness(0),
                        Padding = new Thickness(0),
                        FontSize = 25, // Adjust the font size as needed
                        HorizontalContentAlignment = HorizontalAlignment.Center, // Center the text horizontally
                        VerticalContentAlignment = VerticalAlignment.Center // Center the text vertically
                    };

                    Border border = new()
                    {
                        Child = sudokuGridBoxes[i, j],
                        BorderBrush = Brushes.Black,
                        BorderThickness = new Thickness(
                            j % 3 == 0 ? 2 : 0.5,
                            i % 3 == 0 ? 2 : 0.5,
                            j % 3 == 2 ? 2 : 0.5,
                            i % 3 == 2 ? 2 : 0.5)
                    };

                    SudokuGrid.Children.Add(border);
                }
            }
        }
        private int[,] ParseSudokuGrid()
        {
            int[,] board = new int[9, 9];
            for (int i = 0; i < 9; i++)
            {
                for (int j = 0; j < 9; j++)
                {
                    if (int.TryParse(sudokuGridBoxes[i, j].Text, out int number))
                    {
                        board[i, j] = number;
                    }
                    else
                    {
                        board[i, j] = 0;
                    }
                }
            }
            return board;
        }
        private void SolveButton_Click(object sender, RoutedEventArgs e)
        {
            // Solve the parsed Sudoku board
            sudokuBoard = ParseSudokuGrid();
            // Check if the Sudoku board is solvable (i.e., has no conflicts, such as duplicate numbers in rows, columns, or boxes) :


            if (SolveSudoku(sudokuBoard))
            {
                for (int i = 0; i < 9; i++)
                {
                    for (int j = 0; j < 9; j++)
                    {
                        sudokuGridBoxes[i, j].Text = sudokuBoard[i, j].ToString();
                    }
                }
            }
            else
            {
                MessageBox.Show(Properties.Resources.ResourceManager.GetString("NoSolution"));
            }
        }

        private void GenerateButton_Click(object sender, RoutedEventArgs e)
        {
            SudokuGrid.Children.Clear();
            GenerateSudokuGrid();
        }

        private void CheckButton_Click(object sender, RoutedEventArgs e)
        {
            for (int i = 0; i < 9; i++)
            {
                for (int j = 0; j < 9; j++)
                {
                    if (sudokuBoard[i, j].ToString() != sudokuGridBoxes[i, j].Text)
                    {
                        MessageBox.Show(Properties.Resources.ResourceManager.GetString("NotCorrect"));
                        return;
                    }
                }
            }
            MessageBox.Show(Properties.Resources.ResourceManager.GetString("Correct"));
        }
        private void ClearButton_Click(object sender, RoutedEventArgs e)
        {
            SudokuGrid.Children.Clear();
            sudokuBoard = new int[9, 9];
            GenerateSudokuGrid(firstGeneration: true);
        }

    }
}
