from collections import namedtuple
from random import randrange
from sys import argv
import pygame
import numpy
from time import sleep, time

OPCODE_SIZE = 2
MEM_SIZE = 4096
FRAMEBUFFER_PIXELS = (64, 32)
FRAMEBUFFER_SIZE = (FRAMEBUFFER_PIXELS[0] * FRAMEBUFFER_PIXELS[1]) // 8
FRAMEBUFFER_START = MEM_SIZE - FRAMEBUFFER_SIZE
START_ADDR = 512
FONT_ADDR = 432
FONT_LINES = 5

BLACK = pygame.Color(0, 0, 0)
WHITE = pygame.Color(255, 255, 255)

Opcode = namedtuple("Opcode", ['prefix', 'nnn', 'nn', 'n', 'x', 'y'])

class Machine:
    def __init__(self, display, tone_generator):
        self.memory = bytearray(MEM_SIZE)
        self.program_counter = START_ADDR
        self.register_v = [0] * 16
        self.register_i = 0
        self.timer_delay = 0
        self.timer_sound = 0
        self.stack = []
        self.display = display
        self.tone_generator = tone_generator
        self.last_timer = time()

    def load(self, data, dest=START_ADDR):
        self.memory[dest:dest+len(data)] = data

    def cycle(self):
        print(hex(self.program_counter))
        opcode = self.memory[self.program_counter:self.program_counter+OPCODE_SIZE]
        self.program_counter += OPCODE_SIZE
        self._timers()
        self._process(opcode)
        print(self.register_v, hex(self.register_i))

    def run(self):
        while True:
            self.cycle()
            sleep(0.001)

    def _timers(self):
        if self.timer_delay > 0 or self.timer_sound > 0:
            time_now = time()
            if time_now - self.last_timer > 1/60:
                if self.timer_delay > 0:
                    self.timer_delay -= 1
                if self.timer_sound > 0:
                    self.timer_sound -= 1
                    if self.timer_sound <= 0:
                        self.tone_generator.stop()
                self.last_timer = time_now

    def _decode(self, opcode):
        prefix = opcode[0] >> 4
        x = opcode[0] & 0xF
        y = opcode[1] >> 4
        nnn = (x << 8) + opcode[1]
        nn = nnn & 0xFF
        n = nn & 0xF
        decoded = Opcode(prefix, nnn, nn, n, x, y)
        print(opcode.hex(), decoded)
        return decoded

    def _process(self, opcode):
        handlers = [
                self._handle_prefix_0,
                self._handle_prefix_1,
                self._handle_prefix_2,
                self._handle_prefix_3,
                self._handle_prefix_4,
                self._handle_prefix_5,
                self._handle_prefix_6,
                self._handle_prefix_7,
                self._handle_prefix_8,
                self._handle_prefix_9,
                self._handle_prefix_A,
                self._handle_prefix_B,
                self._handle_prefix_C,
                self._handle_prefix_D,
                self._handle_prefix_E,
                self._handle_prefix_F,
                ]
        decoded = self._decode(opcode)
        handlers[decoded.prefix](decoded)

    def _handle_prefix_0(self, opcode):
        if opcode.nnn == 0x0E0:
            # Clear screen
            self.memory[FRAMEBUFFER_START:FRAMEBUFFER_START+FRAMEBUFFER_SIZE] = bytes(FRAMEBUFFER_SIZE)
        elif opcode.nnn == 0x0EE:
            # Return from subroutine
            self.program_counter = self.stack.pop()
        else:
            # Call RCA 1802 program
            raise Exception("Unimplementable opcode!")

    def _handle_prefix_1(self, opcode):
        # Jump to NNN
        self.program_counter = opcode.nnn

    def _handle_prefix_2(self, opcode):
        # Call subroutine at NNN
        self.stack.append(self.program_counter)
        self.program_counter = opcode.nnn

    def _handle_prefix_3(self, opcode):
        # Skip next instruction if VX == NN
        if self.register_v[opcode.x] == opcode.nn:
            self.program_counter += OPCODE_SIZE

    def _handle_prefix_4(self, opcode):
        # Skip next instruction if VX != NN
        if self.register_v[opcode.x] != opcode.nn:
            self.program_counter += OPCODE_SIZE

    def _handle_prefix_5(self, opcode):
        if opcode.n == 0:
            # Skip next instruction if VX == VY
            if self.register_v[opcode.x] != self.register_v[opcode.y]:
                self.program_counter += OPCODE_SIZE
        else:
            raise Exception("Unknown opcode!")

    def _handle_prefix_6(self, opcode):
        # Set VX to NN
        self.register_v[opcode.x] = opcode.nn

    def _handle_prefix_7(self, opcode):
        # Add NN to VX
        self.register_v[opcode.x] += opcode.nn
        self.register_v[opcode.x] %= 0xFF

    def _handle_prefix_8(self, opcode):
        if opcode.n == 0:
            # Set VX to VY
            self.register_v[opcode.x] = self.register_v[opcode.y]
        elif opcode.n == 1:
            # Set VX to (VX | VY)
            self.register_v[opcode.x] |= self.register_v[opcode.y]
        elif opcode.n == 2:
            # Set VX to (VX & VY)
            self.register_v[opcode.x] &= self.register_v[opcode.y]
        elif opcode.n == 3:
            # Set VX to (VX ^ VY)
            self.register_v[opcode.x] ^= self.register_v[opcode.y]
        elif opcode.n == 4:
            # Add VY to VX, set VF if carry
            self.register_v[opcode.x] += self.register_v[opcode.y]
            if self.register_v[opcode.x] > 0xFF:
                self.register_v[0xF] = 1
                self.register_v[opcode.x] %= 0xFF
            else:
                self.register_v[0xF] = 0
        elif opcode.n == 5:
            # Subtract VY from VX, set VF if borrow
            self.register_v[opcode.x] -= self.register_v[opcode.y]
            if self.register_v[opcode.x] < 0:
                self.register_v[0xF] = 1
                self.register_v[opcode.x] %= 0xFF
            else:
                self.register_v[0xF] = 0
        elif opcode.n == 6:
            # Shift VX right, set VF to LSB of VX before shift
            self.register_v[0xF] = self.register_v[opcode.x] & 1
            self.register_v[opcode.x] = self.register_v[opcode.x] >> 1
        elif opcode.n == 7:
            # Set VX to (VY - VX), set VF if borrow
            self.register_v[opcode.x] = self.register_v[opcode.y] - self.register_v[opcode.x]
            if self.register_v[opcode.x] < 0:
                self.register_v[0xF] = 1
                self.register_v[opcode.x] %= 0xFF
            else:
                self.register_v[0xF] = 0
        elif opcode.n == 0xE:
            # Shift VX left, set VF to MSB of VX before shift
            self.register_v[0xF] = self.register_v[opcode.x] & 128
            self.register_v[opcode.x] = self.register_v[opcode.x] << 1
        else:
            raise Exception("Unknown opcode!")

    def _handle_prefix_9(self, opcode):
        # Skip next instruction if VX != VY
        if opcode.n == 0:
            if self.register_v[opcode.x] != self.register_v[opcode.y]:
                self.program_counter += OPCODE_SIZE

    def _handle_prefix_A(self, opcode):
        # Set I to NNN
        self.register_i = opcode.nnn

    def _handle_prefix_B(self, opcode):
        # Jump to NNN + V0
        self.program_counter = opcode.nnn + self.register_v[0]

    def _handle_prefix_C(self, opcode):
        # Set VX to (NN & rand)
        self.register_v[opcode.x] = opcode.nn & randrange(256)

    def _handle_prefix_D(self, opcode):
        # Draw N lines to X,Y from sprite at I using XOR. Set VF if pixel cleared
        x_pos = self.register_v[opcode.x] % 64
        y_pos = self.register_v[opcode.y] % 32
        x_byte = (x_pos // 8) % 8
        x_bit = x_pos % 8
        collision = 0
        for n in range(opcode.n):
            line_y_pos = y_pos + n
            if line_y_pos >= 32:
                break
            pixel_addr = FRAMEBUFFER_START+((line_y_pos)*8)+x_byte
            hbyte = self.memory[self.register_i+n] >> x_bit
            ohbyte = self.memory[pixel_addr]
            self.memory[pixel_addr] = ohbyte ^ hbyte
            try:
                if x_bit != 0:
                    pixel_addr += 1
                    if ((pixel_addr - FRAMEBUFFER_START) % 8) != 0:
                        lbyte = (self.memory[self.register_i+n] << (8 - x_bit)) & 0xFF
                        olbyte = self.memory[pixel_addr]
                        self.memory[pixel_addr] = olbyte ^ lbyte
            except IndexError:
                pass
            else:
                lbyte = olbyte = 0
            if (ohbyte & ~hbyte) or (olbyte& ~lbyte):
                collision = 1
        self.register_v[0xF] = collision
        self.display.draw(self.memory[FRAMEBUFFER_START:])

    def _handle_prefix_E(self, opcode):
        if opcode.nn == 0x9E:
            # Skip next instruction if key in VX is pressed
            pass
        elif opcode.nn == 0xA1:
            # Skip next instruction if key in VX isn't pressed
            self.program_counter += OPCODE_SIZE
        else:
            raise Exception("Unknown opcode!")

    def _handle_prefix_F(self, opcode):
        if opcode.nn == 0x07:
            # Set VX to delay timer
            self.register_v[opcode.x] = self.timer_delay
        elif opcode.nn == 0x0A:
            # Wait for key press, store in VX
            pass
        elif opcode.nn == 0x15:
            # Set delay timer to VX
            self.timer_delay = self.register_v[opcode.x]
        elif opcode.nn == 0x18:
            # Set sound timer to VX
            self.timer_sound = self.register_v[opcode.x]
            self.tone_generator.start()
        elif opcode.nn == 0x1E:
            # Add VX to I
            self.register_i += self.register_v[opcode.x]
            self.register_i %= 0xFFF
        elif opcode.nn == 0x29:
            # Set I to location of sprite for character in VX
            self.register_i = FONT_ADDR + (self.register_v[opcode.x] * FONT_LINES)
        elif opcode.nn == 0x33:
            # Store BCD of VX at address in I
            value = self.register_v[opcode.x]
            self.memory[self.register_i] = value // 100
            self.memory[self.register_i+1] = value // 10 % 10
            self.memory[self.register_i+2] = value % 10
        elif opcode.nn == 0x55:
            # Store V0 to VX at address in I
            for x in range(opcode.x+1):
                self.memory[self.register_i+x] = self.register_v[x]
        elif opcode.nn == 0x65:
            # Fill V0 to VX with data at address in I
            for x in range(opcode.x+1):
                self.register_v[x] = self.memory[self.register_i+x]
        else:
            raise Exception("Unknown opcode!")

class Display:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode(FRAMEBUFFER_PIXELS, 0, 8)

    def draw(self, framebuffer):
        frame = pygame.surfarray.pixels2d(self.screen)
        for x in range(FRAMEBUFFER_PIXELS[0]//8):
            for y in range(FRAMEBUFFER_PIXELS[1]):
                byte = framebuffer[(y*8)+x]
                bitstring = "{:08b}".format(byte)
                for i, pixel in enumerate(bitstring):
                    pixel = int(pixel) * 255
                    frame[x*8+i][y] = pixel
        pygame.display.flip()

class ToneGenerator:
    def __init__(self, tone):
        pygame.mixer.pre_init(48000, -16, 1, 1024)
        pygame.mixer.init()
        self.tone = pygame.mixer.Sound(tone)

    def start(self):
        self.stop()
        self.tone.play()

    def stop(self):
        self.tone.stop()

if __name__ == "__main__":
    input_file = argv[1]
    font = open("font.bin", "rb").read()
    tone = open("sound.wav", "rb")
    program = open(input_file, "rb").read()
    tone_generator = ToneGenerator(tone)
    display = Display()
    #display = None
    machine = Machine(display, tone_generator)
    machine.load(font, FONT_ADDR)
    machine.load(program)
    machine.run()
