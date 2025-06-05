import gc9a01
import tft_config
import utime
import proverbs_20 as default_font
import inconsolata_16 as english_font
import math
import gc
import micropython

class CircularTextDisplay:
    def __init__(self, tft=None, debug=0):
        """Initialize circular text display for ESP32 with GC9A01.
        debug: 0 = no debug, 1 = minimal, 2 = verbose"""
        self.debug = debug
        self.tft = tft if tft else self._init_display()
        
        # Screen parameters (240x240 circular)
        self.width = 240
        self.height = 240
        self.radius = 120
        self.center_x = 120
        self.center_y = 120
        
        # Font setup
        self.chinese_font = default_font
        self.english_font = english_font
        self.chinese_char_width = default_font.WIDTH if hasattr(default_font, 'WIDTH') else 20
        self.chinese_char_height = default_font.HEIGHT if hasattr(default_font, 'HEIGHT') else 20
        self.english_char_width = english_font.WIDTH if hasattr(english_font, 'WIDTH') else 11
        self.english_char_height = english_font.HEIGHT if hasattr(english_font, 'HEIGHT') else 16
        self.line_spacing = 4
        self.line_height = max(self.chinese_char_height, self.english_char_height) + self.line_spacing
        
        # Display state
        self.current_line = 0
        self.current_y = 20
        self.current_x = 0
        
        # Colors and timing
        self.text_color = gc9a01.WHITE
        self.bg_color = gc9a01.BLUE
        self.char_delay = 0.005  # Reduced from 0.01 to 0.005 seconds
        
        # Cache for line bounds
        self._bounds_cache = {}
        
        # Check TFT capabilities once
        self.has_write = hasattr(self.tft, 'write')
        self.has_write_len = hasattr(self.tft, 'write_len')
        self.english_map = getattr(self.english_font, 'MAP', '')
        
        # Precompiled punctuation set
        self._punctuation = {0xFF0C, 0xFF0E, 0xFF1A, 0xFF1B, 0xFF01, 0xFF1F, 0x002E, 0x0021, 0x003F}

        if self.debug >= 1:
            gc.collect()
            print("Memory after init:")
            micropython.mem_info()

    def _init_display(self):
        """Initialize the circular display."""
        try:
            start_time = utime.ticks_ms()
            tft = tft_config.config(1)
            tft.init()
            tft.fill(gc9a01.BLUE)
            if self.debug >= 1:
                print(f"Display init time: {utime.ticks_diff(utime.ticks_ms(), start_time)} ms")
            return tft
        except Exception as e:
            print(f"Display initialization failed: {e}")
            raise

    def _get_line_bounds(self, y):
        """Get x-coordinate bounds for a given y, using cache."""
        if y in self._bounds_cache:
            return self._bounds_cache[y]
        
        dy = abs(y - self.center_y)
        if dy >= self.radius:
            bounds = (self.center_x, self.center_x)
        else:
            x_offset = int(math.sqrt(self.radius * self.radius - dy * dy)) - 10
            bounds = (max(0, self.center_x - x_offset), min(self.width, self.center_x + x_offset))
        
        self._bounds_cache[y] = bounds
        return bounds

    def _is_within_circle(self, x, y, width):
        """Check if character is within circular bounds (top corners only)."""
        for dx in (0, width):
            if (x + dx - self.center_x) ** 2 + (y - self.center_y) ** 2 > (self.radius - 5) ** 2:
                return False
        return True

    def _is_chinese_or_punctuation(self, char):
        """Check if character is Chinese or punctuation."""
        if not char:
            return False
        code = ord(char)
        return (0x4E00 <= code <= 0x9FFF) or (code in self._punctuation)

    def _new_line(self):
        """Handle new line, resetting x and checking bounds."""
        self.current_line += 1
        self.current_y += self.line_height
        
        if abs(self.current_y - self.center_y) > self.radius - 10:
            start_time = utime.ticks_ms()
            self.tft.fill(self.bg_color)
            self.current_line = 0
            self.current_y = 20
            self._bounds_cache.clear()
            gc.collect()
            if self.debug >= 1:
                print(f"Screen clear time: {utime.ticks_diff(utime.ticks_ms(), start_time)} ms")
                print("Memory after screen clear:")
                micropython.mem_info()

        self.current_x = self._get_line_bounds(self.current_y)[0]

    def _print_char(self, char):
        """Print a single character, returning True if rendered, False if skipped."""
        if char == '\n':
            self._new_line()
            return False
        
        start_time = utime.ticks_ms() if self.debug >= 2 else 0
        
        # Select font and dimensions
        is_chinese = self._is_chinese_or_punctuation(char)
        font = self.chinese_font if is_chinese else self.english_font
        char_width = self.chinese_char_width if is_chinese else self.english_char_width
        char_height = self.chinese_char_height if is_chinese else self.english_char_height
        
        # Get dynamic character width for Chinese if supported
        if is_chinese and self.has_write_len:
            char_width = self.tft.write_len(font, char) or char_width
        
        # Check line bounds
        x_min, x_max = self._get_line_bounds(self.current_y)
        if self.current_x + char_width > x_max:
            self._new_line()
            x_min, x_max = self._get_line_bounds(self.current_y)
        
        x = self.current_x
        if not self._is_within_circle(x, self.current_y, char_width):
            self._new_line()
            x = self.current_x = self._get_line_bounds(self.current_y)[0]
        
        # Draw character
        try:
            render_start = utime.ticks_ms() if self.debug >= 2 else 0
            self.tft.fill_rect(x, self.current_y, char_width, char_height, self.bg_color)
            if is_chinese and self.has_write:
                self.tft.write(font, char, x, self.current_y, self.text_color, self.bg_color)
            elif not is_chinese and char in self.english_map:
                char_index = self.english_font.MAP.index(char)
                self.tft.bitmap(font, x, self.current_y, char_index)
            else:
                return False
            render_time = utime.ticks_diff(utime.ticks_ms(), render_start) if self.debug >= 2 else 0
            if self.debug >= 2 and render_time > 10:
                print(f"High render time for '{char}': {render_time} ms (write/bitmap)")
        except (AttributeError, ValueError) as e:
            if self.debug >= 1:
                print(f"Failed to render '{char}': {e}")
            return False
        
        self.current_x += char_width
        if self.debug >= 2:
            total_time = utime.ticks_diff(utime.ticks_ms(), start_time)
            print(f"Char '{char}' render time: {total_time} ms")
            if total_time > 10:
                print(f"High total render time for '{char}': {total_time} ms")
            gc.collect()
            print(f"Memory after rendering '{char}':")
            micropython.mem_info()
        
        return True

    def display_text(self, text, color=None, bg_color=None, char_delay=None):
        """Display text character by character or in batches."""
        start_time = utime.ticks_ms()
        
        self.text_color = color or self.text_color
        self.bg_color = bg_color or self.bg_color
        self.char_delay = char_delay if char_delay is not None else self.char_delay
        
        self.tft.fill(self.bg_color)
        self.current_line = 0
        self.current_y = 20
        self.current_x = self._get_line_bounds(self.current_y)[0]
        self._bounds_cache.clear()
        
        # Batch rendering: process one line at a time
        line_buffer = []
        line_width = 0
        x_min, x_max = self._get_line_bounds(self.current_y)
        
        for char in text:
            if char == '\n':
                if line_buffer:
                    self._render_line(line_buffer, line_width)
                    line_buffer.clear()
                    line_width = 0
                self._new_line()
                x_min, x_max = self._get_line_bounds(self.current_y)
                continue
            
            is_chinese = self._is_chinese_or_punctuation(char)
            char_width = self.chinese_char_width if is_chinese else self.english_char_width
            if is_chinese and self.has_write_len:
                char_width = self.tft.write_len(self.chinese_font, char) or char_width
            
            if self.current_x + line_width + char_width > x_max or not self._is_within_circle(self.current_x + line_width, self.current_y, char_width):
                if line_buffer:
                    self._render_line(line_buffer, line_width)
                    line_buffer.clear()
                    line_width = 0
                self._new_line()
                x_min, x_max = self._get_line_bounds(self.current_y)
            
            line_buffer.append(char)
            line_width += char_width
        
        # Render any remaining characters
        if line_buffer:
            self._render_line(line_buffer, line_width)
        
        gc.collect()
        if self.debug >= 1:
            print(f"Total display_text time: {utime.ticks_diff(utime.ticks_ms(), start_time)} ms")
            print("Memory after display_text:")
            micropython.mem_info()

    def _render_line(self, line_buffer, line_width):
        """Render a line of characters with a single delay."""
        start_time = utime.ticks_ms() if self.debug >= 2 else 0
        for char in line_buffer:
            self._print_char(char)
        if self.char_delay > 0:
            utime.sleep(self.char_delay * len(line_buffer))
        if self.debug >= 2:
            print(f"Line render time for {len(line_buffer)} chars: {utime.ticks_diff(utime.ticks_ms(), start_time)} ms")

    def clear_screen(self):
        """Clear the screen and reset state."""
        start_time = utime.ticks_ms()
        self.tft.fill(self.bg_color)
        self.current_line = 0
        self.current_y = 20
        self.current_x = self._get_line_bounds(self.current_y)[0]
        self._bounds_cache.clear()
        gc.collect()
        if self.debug >= 1:
            print(f"Clear screen time: {utime.ticks_diff(utime.ticks_ms(), start_time)} ms")
            print("Memory after clear_screen:")
            micropython.mem_info()
'''
if __name__ == "__main__":
    try:
        display = CircularTextDisplay(debug=1)
        test_text = """这是一个由虾哥开源的ESP32项目，以MIT许可证发布，允许任何人免费使用，或用于商业用途。We hope this project helps you understand AI hardware development and apply large language models to real devices. 如果你有任何想法或建议，请随时提出Issues或加入QQ群：575180511"""
        display.display_text(
            text=test_text,
            color=gc9a01.YELLOW,
            bg_color=gc9a01.BLUE,
            char_delay=0.005
        )
        display.clear_screen()
        print("Test completed")
    except Exception as e:
        print(f"Test failed: {e}")
'''
