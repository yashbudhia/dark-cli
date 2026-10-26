// A disposable native Windows target. It deliberately accepts negative quantities.
using System;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Windows.Forms;

public static class FixtureApp
{
    [DllImport("user32.dll")]
    private static extern bool SetProcessDPIAware();

    [STAThread]
    public static void Main()
    {
        SetProcessDPIAware();
        Application.EnableVisualStyles();
        var form = new Form {
            Text = "Dark Desktop Fixture", Width = 500, Height = 280,
            StartPosition = FormStartPosition.CenterScreen
        };
        var description = new Label {
            Text = "Inventory test target - negative quantities should be rejected.",
            Left = 24, Top = 24, Width = 440, Height = 32
        };
        var quantity = new TextBox {
            Name = "quantityInput", AccessibleName = "Quantity",
            Left = 24, Top = 72, Width = 220, Text = "1"
        };
        var status = new Label {
            Name = "statusLabel",
            Left = 24, Top = 170, Width = 440, Height = 40, Text = "Ready"
        };
        var save = new Button {
            Name = "saveButton", Text = "Save", Left = 24, Top = 115, Width = 100
        };
        var reset = new Button {
            Name = "resetButton", Text = "Reset", Left = 140, Top = 115, Width = 100
        };
        save.Click += delegate {
            int value;
            // Intentional bug for the regression demo: missing value >= 0 check.
            status.Text = int.TryParse(quantity.Text, out value)
                ? "Saved quantity: " + value : "Rejected: enter an integer";
        };
        reset.Click += delegate { quantity.Text = "1"; status.Text = "Ready"; };
        form.Controls.AddRange(new Control[] { description, quantity, save, reset, status });
        Application.Run(form);
    }
}
