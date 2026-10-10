namespace Brasscribe.ScreenCheck;

/// <summary>A screenshot as 8-bit BGRA rows, top to bottom (the layout of RenderTargetBitmap and GDI+).</summary>
public sealed class Picture(int width, int height, byte[] bgra)
{
    public int Width { get; } = width;
    public int Height { get; } = height;
    public byte[] Bgra { get; } = bgra.Length == width * height * 4 ? bgra : throw new ArgumentException("BGRA size does not match the picture");

    public static Picture Blank(int width, int height, uint argb = 0xFFFFFFFF)
    {
        var bytes = new byte[width * height * 4];
        var p = new Picture(width, height, bytes);
        p.Fill(new Box(0, 0, width, height), argb);
        return p;
    }

    /// <summary>The pixel at (x, y) as 0xAARRGGBB.</summary>
    public uint this[int x, int y]
    {
        get
        {
            int i = (y * Width + x) * 4;
            return (uint)Bgra[i + 3] << 24 | (uint)Bgra[i + 2] << 16 | (uint)Bgra[i + 1] << 8 | Bgra[i];
        }
        set
        {
            int i = (y * Width + x) * 4;
            Bgra[i] = (byte)value;
            Bgra[i + 1] = (byte)(value >> 8);
            Bgra[i + 2] = (byte)(value >> 16);
            Bgra[i + 3] = (byte)(value >> 24);
        }
    }

    public void Fill(Box box, uint argb)
    {
        var b = box.Within(Width, Height);
        for (int y = b.Y; y < b.Bottom; y++)
            for (int x = b.X; x < b.Right; x++)
                this[x, y] = argb;
    }

    /// <summary>
    /// Draws <paramref name="over"/> (premultiplied BGRA, as RenderTargetBitmap gives it) at (<paramref name="left"/>,
    /// <paramref name="top"/>): how an open dialog or flyout, drawn on its own, goes on top of the window's picture.
    /// </summary>
    public void Compose(Picture over, int left, int top)
    {
        for (int y = Math.Max(0, -top); y < over.Height && y + top < Height; y++)
            for (int x = Math.Max(0, -left); x < over.Width && x + left < Width; x++)
            {
                int s = (y * over.Width + x) * 4, d = ((y + top) * Width + x + left) * 4;
                int a = over.Bgra[s + 3];
                if (a == 0) continue;
                for (int c = 0; c < 3; c++) Bgra[d + c] = (byte)Math.Min(255, over.Bgra[s + c] + Bgra[d + c] * (255 - a) / 255);
                Bgra[d + 3] = 255;
            }
    }

    /// <summary>The same pixels: two pictures of one screen that a person could not tell apart.</summary>
    public bool SameAs(Picture other) => Width == other.Width && Height == other.Height && Bgra.AsSpan().SequenceEqual(other.Bgra);
}

/// <summary>A rectangle in pixels.</summary>
public readonly record struct Box(int X, int Y, int Width, int Height)
{
    public int Right => X + Width;
    public int Bottom => Y + Height;
    public bool IsEmpty => Width <= 0 || Height <= 0;

    /// <summary>The part inside a picture of this size.</summary>
    public Box Within(int width, int height)
    {
        int x = Math.Clamp(X, 0, width), y = Math.Clamp(Y, 0, height);
        return new Box(x, y, Math.Clamp(Right, 0, width) - x, Math.Clamp(Bottom, 0, height) - y);
    }

    /// <summary>From a rectangle in device-independent pixels at a display scale, rounded outwards.</summary>
    public static Box FromDips(double x, double y, double width, double height, double scale)
    {
        int left = (int)Math.Floor(x * scale), top = (int)Math.Floor(y * scale);
        return new Box(left, top, (int)Math.Ceiling((x + width) * scale) - left, (int)Math.Ceiling((y + height) * scale) - top);
    }
}
