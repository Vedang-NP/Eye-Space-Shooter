"""
main_game.py
============
A basic rocket shooter game where the rocket movement is controlled by
eye gaze (captured via webcam in real time).

Features:
    - Home page with a PLAY button.
    - After clicking PLAY, the game begins with eye tracking.
    - Rocket moves left/right based on gaze direction.
    - Arrow keys work as a fallback control.
    - Asteroids fall from the top; shoot them before they hit the rocket.
    - Score + lives, easy difficulty.
    - Live webcam overlay showing the gaze detection.
    - Press P to return to the menu, Q to quit (or ESC).
"""

import math
import random
import sys

import cv2
import numpy as np
import pygame

from eye_tracker import EyeTracker


# -----------------------------
# Constants
# -----------------------------

WIDTH, HEIGHT = 900, 650

# Colors
BLACK = (10, 10, 20)
WHITE = (255, 255, 255)
RED = (255, 60, 60)
GREEN = (60, 255, 60)
BLUE = (80, 160, 255)
YELLOW = (255, 220, 80)
ORANGE = (255, 150, 60)
GRAY = (120, 120, 130)
MUTED = (150, 160, 190)      # secondary UI text
PANEL_EDGE = (120, 150, 220)

# Gameplay
ROCKET_SPEED = 14
BULLET_SPEED = 12
ASTEROID_SPEED = 6
ASTEROID_MIN_RADIUS = 24
ASTEROID_MAX_RADIUS = 51
ASTEROID_SPAWN = 40          # frames between spawns (higher = fewer = easier)
BULLET_COOLDOWN = 12
START_LIVES = 5

# Webcam overlay size (shown in the corner)
CAM_W, CAM_H = 200, 150


# -----------------------------
# Helper functions
# -----------------------------

_font_cache = {}
_text_cache = {}
_panel_cache = {}
_glow_cache = {}


def get_font(size):
    if size not in _font_cache:
        _font_cache[size] = pygame.font.SysFont("avenirnext,helveticaneue,arial", size, bold=True)
    return _font_cache[size]


def render_text(text, size, color):
    key = (text, size, color)
    if key not in _text_cache:
        if len(_text_cache) > 400:
            _text_cache.clear()
        _text_cache[key] = get_font(size).render(text, True, color)
    return _text_cache[key]


def draw_text(surface, text, size, color, x, y, anchor="center", shadow=True):
    """Draw text with `anchor` (any pygame Rect attribute) placed at (x, y)."""
    img = render_text(text, size, color)
    rect = img.get_rect(**{anchor: (x, y)})
    if shadow:
        surface.blit(render_text(text, size, (0, 0, 8)), rect.move(0, 2))
    surface.blit(img, rect)


def draw_title(surface, text, size, color, x, y, depth=6):
    """Extruded headline: darker copies stepped down-right behind the face."""
    side = tuple(int(c * 0.35) for c in color)
    for i in range(depth, 0, -1):
        draw_text(surface, text, size, side, x + i, y + i, shadow=False)
    draw_text(surface, text, size, color, x, y, shadow=False)


def draw_panel(surface, rect, radius=14):
    """Translucent glass panel with a thin border and a top highlight."""
    key = (rect.w, rect.h, radius)
    if key not in _panel_cache:
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        box = panel.get_rect()
        pygame.draw.rect(panel, (18, 24, 46, 185), box, border_radius=radius)
        pygame.draw.rect(panel, (*PANEL_EDGE, 110), box, 1, border_radius=radius)
        pygame.draw.line(panel, (255, 255, 255, 40), (radius, 1), (rect.w - radius, 1))
        _panel_cache[key] = panel
    surface.blit(_panel_cache[key], rect)


def draw_button(surface, rect, label, hover):
    """Raised button: a darker slab underneath gives it thickness."""
    pygame.draw.rect(surface, (18, 105, 58), rect.move(0, 6), border_radius=14)
    pygame.draw.rect(surface, (78, 228, 128) if hover else (52, 200, 102), rect, border_radius=14)
    gloss = pygame.Surface((rect.w - 8, rect.h // 2 - 2), pygame.SRCALPHA)
    pygame.draw.rect(gloss, (255, 255, 255, 50), gloss.get_rect(), border_radius=10)
    surface.blit(gloss, (rect.x + 4, rect.y + 3))
    pygame.draw.rect(surface, (205, 255, 222), rect, 2, border_radius=14)
    draw_text(surface, label, 28, (8, 44, 26), rect.centerx, rect.centery, shadow=False)


def get_glow(radius, color):
    """Soft round light, meant to be blitted with BLEND_RGB_ADD."""
    key = (radius, color)
    if key not in _glow_cache:
        ys, xs = np.mgrid[-radius:radius, -radius:radius].astype(np.float32) / radius
        falloff = np.clip(1 - np.hypot(xs, ys), 0, 1) ** 2
        rgb = (falloff[..., None] * np.array(color)).astype(np.uint8)
        _glow_cache[key] = pygame.surfarray.make_surface(rgb.swapaxes(0, 1)).convert()
    return _glow_cache[key]


def draw_glow(surface, x, y, radius, color):
    surface.blit(get_glow(radius, color), (int(x) - radius, int(y) - radius),
                 special_flags=pygame.BLEND_RGB_ADD)


def make_heart(size, color):
    """Small shaded heart icon, drawn at 4x and scaled down for smooth edges."""
    k = 4
    s = size * k
    big = pygame.Surface((s, s), pygame.SRCALPHA)
    r = s // 4
    pygame.draw.circle(big, color, (r, r + 2), r)
    pygame.draw.circle(big, color, (s - r, r + 2), r)
    pygame.draw.polygon(big, color, [(1, r + r // 2), (s - 1, r + r // 2), (s // 2, s - 2)])
    pygame.draw.circle(big, tuple(min(255, c + 90) for c in color), (r - r // 4, r - r // 6 + 2), r // 3)
    return pygame.transform.smoothscale(big, (size, size))


class Background:
    """Nebula backdrop plus three star layers scrolling at different speeds,
    so nearer stars drift faster than distant ones."""

    def __init__(self):
        self.base = self._make_base()
        self.tick = 0
        self.layers = []
        # (scroll speed, star count, size, brightness) from far to near
        for speed, count, size, bright in [(0.15, 90, 1, 105), (0.40, 50, 1, 175), (0.90, 22, 2, 245)]:
            stars = [[random.uniform(0, WIDTH), random.uniform(0, HEIGHT), random.uniform(0, 6.28)]
                     for _ in range(count)]
            self.layers.append((speed, size, bright, stars))

    @staticmethod
    def _make_base():
        def noise(cells):
            grid = np.random.rand(cells, cells).astype(np.float32)
            return cv2.resize(grid, (WIDTH, HEIGHT), interpolation=cv2.INTER_CUBIC)

        def cloud():
            return np.clip(0.7 * noise(5) + 0.3 * noise(11) - 0.45, 0, 1) ** 1.5

        fade = np.linspace(0, 1, HEIGHT, dtype=np.float32)[:, None, None]
        img = np.array([6, 8, 20], np.float32) + fade * np.array([10, 4, 14], np.float32)
        img = np.broadcast_to(img, (HEIGHT, WIDTH, 3)).copy()
        img += cloud()[..., None] * np.array([75, 30, 115], np.float32)   # violet
        img += cloud()[..., None] * np.array([18, 60, 110], np.float32)   # blue
        img = np.clip(img, 0, 255).astype(np.uint8)
        return pygame.surfarray.make_surface(img.swapaxes(0, 1)).convert()

    def update(self):
        self.tick += 1
        for speed, _, _, stars in self.layers:
            for star in stars:
                star[1] += speed
                if star[1] > HEIGHT:
                    star[0], star[1] = random.uniform(0, WIDTH), 0

    def draw(self, surface):
        surface.blit(self.base, (0, 0))
        for _, size, bright, stars in self.layers:
            for x, y, phase in stars:
                c = int(bright * (0.8 + 0.2 * math.sin(self.tick * 0.05 + phase)))
                surface.fill((c, c, min(255, c + 15)), (int(x), int(y), size, size))


# -----------------------------
# Game object classes
# -----------------------------

class Rocket:
    def __init__(self):
        self.width = 50
        self.height = 60
        self.x = WIDTH // 2 - self.width // 2
        self.y = HEIGHT - self.height - 30
        self.speed = ROCKET_SPEED

    def move(self, dx):
        self.x += dx
        self.x = max(0, min(WIDTH - self.width, self.x))

    @property
    def center_x(self):
        return self.x + self.width // 2

    _sprite = None
    _PAD = 10   # sprite is wider than the hit box so the fins fit

    @classmethod
    def _build_sprite(cls):
        """Render the rocket once at 4x and scale it down. Round parts get
        cylinder shading lit from the upper left, matching the asteroids."""
        k, pad = 4, cls._PAD
        w, h = (50 + 2 * pad) * k, 60 * k
        rgba = np.zeros((h, w, 4), dtype=np.float32)
        xs = np.arange(w)[None, :]

        def paint(points, base, rounded=True, dim=1.0):
            mask_surf = pygame.Surface((w, h))
            pygame.draw.polygon(mask_surf, (255, 255, 255),
                                [((x + pad) * k, y * k) for x, y in points])
            mask = pygame.surfarray.array3d(mask_surf)[:, :, 0].T > 0
            if rounded:
                # Position across the part on each row, -1 (left) to 1 (right)
                left = mask.argmax(1)
                right = w - 1 - mask[:, ::-1].argmax(1)
                mid = (left + right) / 2
                half = np.maximum((right - left) / 2, 1)
                u = np.clip((xs - mid[:, None]) / half[:, None], -1, 1)
                light = (0.30 + 0.70 * np.clip(-0.55 * u + 0.8 * np.sqrt(1 - u * u), 0, 1)
                         + 0.30 * np.exp(-((u + 0.45) / 0.16) ** 2))
            else:
                light = np.full((h, w), dim)
            color = np.clip(np.array(base)[None, None, :] * light[..., None], 0, 255)
            rgba[mask, :3] = color[mask]
            rgba[mask, 3] = 255

        def circle(cx, cy, r):
            return [(cx + r * np.cos(a), cy + r * np.sin(a))
                    for a in np.linspace(0, 6.28, 32, endpoint=False)]

        # Side fins (flat plates: lit side bright, far side in shadow)
        paint([(10, 34), (-7, 54), (-7, 60), (10, 52)], BLUE, rounded=False, dim=1.0)
        paint([(40, 34), (57, 54), (57, 60), (40, 52)], BLUE, rounded=False, dim=0.55)
        # Engine nozzle, body, red band
        paint([(17, 54), (33, 54), (36, 60), (14, 60)], (110, 110, 120))
        paint([(10, 20), (40, 20), (40, 55), (10, 55)], (235, 235, 240))
        paint([(10, 23), (40, 23), (40, 27), (10, 27)], RED)
        # Curved nose cone
        rows = np.linspace(0, 20, 16)
        widths = 15 * np.sin(np.pi / 2 * rows / 20) ** 0.8
        paint([(25 - hw, y) for hw, y in zip(widths, rows)]
              + [(25 + hw, y) for hw, y in zip(widths[::-1], rows[::-1])], RED)
        # Fin facing the viewer
        paint([(24, 43), (26, 43), (26.5, 58), (23.5, 58)], BLUE, rounded=False, dim=0.8)
        # Porthole: metal ring, glass, glint
        paint(circle(25, 36, 7), (190, 190, 200), rounded=False)
        paint(circle(25, 36, 5), (40, 90, 160), rounded=False)
        paint(circle(23.2, 34.2, 1.6), (210, 235, 255), rounded=False)

        big = pygame.image.frombuffer(rgba.astype(np.uint8).tobytes(), (w, h), "RGBA")
        return pygame.transform.smoothscale(big.convert_alpha(), (w // k, h // k))

    @classmethod
    def sprite(cls):
        if cls._sprite is None:
            cls._sprite = cls._build_sprite()
        return cls._sprite

    def draw(self, surface):
        cx = self.center_x
        base_y = self.y + self.height - 1
        draw_glow(surface, cx, base_y + 6, 26, (120, 60, 15))
        # Exhaust flame (animated flicker)
        flame = random.randint(8, 16)
        pygame.draw.polygon(surface, ORANGE,
                            [(cx - 7, base_y), (cx + 7, base_y), (cx, base_y + flame)])
        pygame.draw.polygon(surface, YELLOW,
                            [(cx - 3, base_y), (cx + 3, base_y), (cx, base_y + flame // 2)])
        surface.blit(self.sprite(), (self.x - self._PAD, self.y))


class Bullet:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.w = 6
        self.h = 16
        self.speed = BULLET_SPEED

    def update(self):
        self.y -= self.speed

    def draw(self, surface):
        draw_glow(surface, self.x, self.y + self.h // 2, 16, (130, 80, 15))
        pygame.draw.rect(surface, YELLOW, (self.x - self.w // 2, self.y, self.w, self.h), border_radius=3)
        pygame.draw.rect(surface, WHITE, (self.x - 1, self.y + 2, 2, self.h - 5), border_radius=1)

    @property
    def rect(self):
        return pygame.Rect(self.x - self.w // 2, self.y, self.w, self.h)


class Asteroid:
    def __init__(self, radius=None):
        self.radius = radius or random.randint(ASTEROID_MIN_RADIUS, ASTEROID_MAX_RADIUS)
        self.x = random.randint(self.radius, WIDTH - self.radius)
        self.y = -self.radius * 2
        self.speed = random.uniform(ASTEROID_SPEED * 0.6, ASTEROID_SPEED * 1.3)
        self.vert_speed = random.uniform(-0.5, 0.5)
        self.rotation = random.uniform(0, 360)
        self.rot_speed = random.uniform(-2, 2)
        self.sprite = self._make_sprite()
        self.light = self._light_map(self.sprite.get_width())

    def _make_sprite(self):
        """Build the unlit rock texture (lumpy outline, mottling, craters)."""
        r = self.radius
        half = int(r * 1.25) + 2
        size = half * 2
        ys, xs = np.mgrid[-half:half, -half:half].astype(np.float32)
        dist = np.hypot(xs, ys)
        theta = np.arctan2(ys, xs)

        # Lumpy outline: a few low-frequency waves around the circle
        edge = np.ones_like(theta)
        for k in range(2, 6):
            edge += random.uniform(0.02, 0.07) * np.sin(k * theta + random.uniform(0, 6.28))
        edge = np.minimum(edge, 1.22) * r

        # Surface mottling: random grids blown up to sprite size, three scales
        def noise(cells):
            grid = np.random.rand(cells, cells).astype(np.float32)
            return cv2.resize(grid, (size, size), interpolation=cv2.INTER_CUBIC)

        tone = 0.7 + 0.5 * (0.6 * noise(4) + 0.3 * noise(9) + 0.1 * noise(24))

        # Craters: dark floor with a bright rim
        for _ in range(random.randint(3, 6)):
            cr = r * random.uniform(0.10, 0.24)
            ang = random.uniform(0, 6.28)
            off = r * random.uniform(0, 0.6)
            cd = np.hypot(xs - off * np.cos(ang), ys - off * np.sin(ang)) / cr
            tone *= 1 - 0.4 * np.sqrt(np.clip(1 - cd, 0, 1))
            tone *= 1 + 0.25 * np.exp(-((cd - 1.05) / 0.12) ** 2)

        # Darken towards the outline so the lumps read as rounded
        depth = np.clip((edge - dist) / (edge * 0.35), 0, 1)
        tone *= 0.65 + 0.35 * depth * depth * (3 - 2 * depth)

        base = np.array([random.uniform(205, 235), random.uniform(190, 215),
                         random.uniform(170, 200)], dtype=np.float32)
        rgba = np.empty((size, size, 4), dtype=np.uint8)
        rgba[..., :3] = np.clip(tone[..., None] * base, 0, 255)
        rgba[..., 3] = np.clip(edge - dist, 0, 1) * 255
        return pygame.image.frombuffer(rgba.tobytes(), (size, size), "RGBA").convert_alpha()

    _light_cache = {}

    @classmethod
    def _light_map(cls, size):
        """Sphere shading lit from the upper left. It is multiplied over the
        rotated sprite, so the rock spins while the light stays put."""
        if size not in cls._light_cache:
            half = size / 2
            ys, xs = np.mgrid[-half:half, -half:half].astype(np.float32) / half
            nz = np.sqrt(np.clip(1 - xs * xs - ys * ys, 0, 1))
            lit = np.clip(-0.55 * xs - 0.60 * ys + 0.58 * nz, 0, 1) ** 0.8
            rgba = np.full((size, size, 4), 255, dtype=np.uint8)
            rgba[..., :3] = ((0.25 + 0.75 * lit) * 255)[..., None]
            cls._light_cache[size] = pygame.image.frombuffer(
                rgba.tobytes(), (size, size), "RGBA").convert_alpha()
        return cls._light_cache[size]

    def update(self):
        self.y += self.speed
        self.x += self.vert_speed
        self.rotation += self.rot_speed
        if self.x < self.radius or self.x > WIDTH - self.radius:
            self.vert_speed *= -1

    def draw(self, surface):
        sprite = pygame.transform.rotozoom(self.sprite, self.rotation, 1)
        sprite.blit(self.light, self.light.get_rect(center=sprite.get_rect().center),
                    special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(sprite, sprite.get_rect(center=(int(self.x), int(self.y))))

    @property
    def rect(self):
        return pygame.Rect(self.x - self.radius, self.y - self.radius,
                           self.radius * 2, self.radius * 2)


class Blast:
    """Short fading puff shown where an asteroid was shot."""

    LIFE = 18   # frames

    def __init__(self, x, y, radius):
        self.x = x
        self.y = y
        self.radius = radius
        self.age = 0
        # (direction in degrees, speed factor) for each bit of debris
        self.sparks = [(random.uniform(0, 360), random.uniform(0.6, 1.3)) for _ in range(8)]

    def update(self):
        self.age += 1

    @property
    def done(self):
        return self.age >= self.LIFE

    def draw(self, surface):
        t = self.age / self.LIFE
        alpha = int(190 * (1 - t))
        half = int(self.radius * 1.8) + 4
        layer = pygame.Surface((half * 2, half * 2), pygame.SRCALPHA)

        # Brief soft flash, then an expanding ring
        if t < 0.4:
            pygame.draw.circle(layer, (255, 235, 190, int(120 * (1 - t / 0.4))),
                               (half, half), int(self.radius * 0.6))
        pygame.draw.circle(layer, (255, 200, 120, alpha), (half, half),
                           int(self.radius * (0.5 + 0.9 * t)), 2)

        # Debris drifting outwards
        for angle, speed in self.sparks:
            v = pygame.math.Vector2(1, 0).rotate(angle) * self.radius * (0.3 + 1.1 * t * speed)
            pygame.draw.circle(layer, (200, 190, 175, alpha),
                               (int(half + v.x), int(half + v.y)), 2)

        surface.blit(layer, (int(self.x) - half, int(self.y) - half))


# -----------------------------
# Game states
# -----------------------------

class Game:
    STATE_HOME = "home"
    STATE_PLAYING = "playing"
    STATE_GAME_OVER = "game_over"

    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Eye-Controlled Rocket Shooter")
        self.clock = pygame.time.Clock()
        self.state = self.STATE_HOME

        self.background = Background()
        self.heart_full = make_heart(22, RED)
        self.heart_empty = make_heart(22, (62, 44, 60))
        self.hero = pygame.transform.smoothscale(Rocket.sprite(), (140, 120))
        self.hit_flash = 0          # frames of red flash left after losing a life
        self.best = 0

        # Game objects (reset on play)
        self.rocket = Rocket()
        self.bullets = []
        self.asteroids = []
        self.blasts = []
        self.score = 0
        self.lives = START_LIVES
        self.frame_count = 0
        self.shoot_cooldown = 0
        self.gaze_dir = "No Face"

        # Eye tracker (webcam)
        self.tracker = EyeTracker()
        self.tracker.start()

        # Play button rect
        self.play_btn = pygame.Rect(WIDTH // 2 - 110, 468, 220, 60)

    # ----------------------------------------------------------
    # Core loop
    # ----------------------------------------------------------

    def run(self):
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if self.state != self.STATE_PLAYING and self.play_btn.collidepoint(event.pos):
                        self.start_game()
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE or event.key == pygame.K_q:
                        running = False
                    elif event.key == pygame.K_p and self.state == self.STATE_PLAYING:
                        self.state = self.STATE_HOME
                    elif event.key == pygame.K_RETURN and self.state != self.STATE_PLAYING:
                        self.start_game()

            self.background.update()
            if self.state == self.STATE_PLAYING:
                self.update()
                self.draw_game()
            else:
                self.draw_ui()

            pygame.display.flip()
            self.clock.tick(60)

        self.tracker.stop()
        pygame.quit()
        sys.exit()

    # ----------------------------------------------------------
    # Game setup
    # ----------------------------------------------------------

    def start_game(self):
        self.rocket = Rocket()
        self.bullets = []
        self.asteroids = []
        self.blasts = []
        self.score = 0
        self.lives = START_LIVES
        self.frame_count = 0
        self.shoot_cooldown = 0
        self.hit_flash = 0
        self.state = self.STATE_PLAYING

    # ----------------------------------------------------------
    # Update logic
    # ----------------------------------------------------------

    def update(self):
        self.frame_count += 1
        self.gaze_dir, _, _ = self.tracker.get_state()

        keys = pygame.key.get_pressed()

        # --- Movement (eye gaze primary, keyboard fallback) ---
        dx = 0
        if self.gaze_dir == "Left":
            dx -= self.rocket.speed
        elif self.gaze_dir == "Right":
            dx += self.rocket.speed

        # Keyboard always overrides eye control when pressed
        if keys[pygame.K_LEFT]:
            dx = -self.rocket.speed
        elif keys[pygame.K_RIGHT]:
            dx = self.rocket.speed

        self.rocket.move(dx)

        # --- Shooting ---
        self.shoot_cooldown = max(0, self.shoot_cooldown - 1)
        if (keys[pygame.K_SPACE] or self.gaze_dir == "Center") and self.shoot_cooldown == 0:
            self.bullets.append(Bullet(self.rocket.center_x, self.rocket.y))
            self.shoot_cooldown = BULLET_COOLDOWN

        # --- Update bullets ---
        for b in self.bullets:
            b.update()
        self.bullets = [b for b in self.bullets if b.y > -20]

        # --- Spawn asteroids ---
        if self.frame_count % ASTEROID_SPAWN == 0:
            self.asteroids.append(Asteroid())

        # --- Update asteroids ---
        for a in self.asteroids:
            a.update()

        # --- Collisions: bullets vs asteroids ---
        remaining_bullets = []
        for b in self.bullets:
            hit = False
            for a in self.asteroids:
                if b.rect.colliderect(a.rect):
                    hit = True
                    self.score += 1
                    self.asteroids.remove(a)
                    self.blasts.append(Blast(a.x, a.y, a.radius))
                    break
            if not hit:
                remaining_bullets.append(b)
        self.bullets = remaining_bullets

        # --- Collisions: rocket vs asteroids ---
        rocket_rect = pygame.Rect(self.rocket.x, self.rocket.y,
                                  self.rocket.width, self.rocket.height)
        for a in self.asteroids[:]:
            if a.rect.colliderect(rocket_rect):
                self.asteroids.remove(a)
                self.blasts.append(Blast(a.x, a.y, a.radius))
                self.hit_flash = 14
                self.lives -= 1
                if self.lives <= 0:
                    self.best = max(self.best, self.score)
                    self.state = self.STATE_GAME_OVER

        # --- Update asteroids that fell off screen ---
        self.asteroids = [a for a in self.asteroids if a.y < HEIGHT + a.radius * 1.2]

        # --- Update blasts ---
        for bl in self.blasts:
            bl.update()
        self.blasts = [bl for bl in self.blasts if not bl.done]

    # ----------------------------------------------------------
    # Drawing
    # ----------------------------------------------------------

    def draw_ui(self):
        self.gaze_dir = self.tracker.get_direction()
        self.background.draw(self.screen)
        cx = WIDTH // 2
        hover = self.play_btn.collidepoint(pygame.mouse.get_pos())

        if self.state == self.STATE_HOME:
            # Hovering rocket
            bob = math.sin(pygame.time.get_ticks() / 450) * 6
            hero = self.hero.get_rect(center=(cx, 105 + bob))
            draw_glow(self.screen, cx, hero.bottom + 8, 60, (120, 60, 15))
            flame = random.randint(18, 30)
            pygame.draw.polygon(self.screen, ORANGE, [(cx - 14, hero.bottom - 2),
                                                      (cx + 14, hero.bottom - 2),
                                                      (cx, hero.bottom + flame)])
            pygame.draw.polygon(self.screen, YELLOW, [(cx - 6, hero.bottom - 2),
                                                      (cx + 6, hero.bottom - 2),
                                                      (cx, hero.bottom + flame // 2)])
            self.screen.blit(self.hero, hero)

            draw_text(self.screen, "E Y E - C O N T R O L L E D", 16, BLUE, cx, 212)
            draw_title(self.screen, "ROCKET SHOOTER", 68, WHITE, cx, 262)

            panel = pygame.Rect(cx - 250, 322, 500, 118)
            draw_panel(self.screen, panel)
            rows = [("LOOK LEFT / RIGHT", "steer the rocket"),
                    ("LOOK CENTER", "fire"),
                    ("ARROW KEYS + SPACE", "keyboard fallback")]
            for i, (key, action) in enumerate(rows):
                y = panel.y + 28 + i * 31
                draw_text(self.screen, key, 17, WHITE, panel.x + 28, y, anchor="midleft")
                draw_text(self.screen, action, 17, MUTED, panel.right - 28, y, anchor="midright")

            draw_button(self.screen, self.play_btn, "PLAY", hover)
            draw_text(self.screen, "ENTER  play      P  menu      Q / ESC  quit", 14, MUTED,
                      cx, HEIGHT - 28)

        elif self.state == self.STATE_GAME_OVER:
            draw_title(self.screen, "GAME OVER", 76, RED, cx, 170)

            panel = pygame.Rect(cx - 190, 250, 380, 170)
            draw_panel(self.screen, panel)
            draw_text(self.screen, "FINAL SCORE", 16, MUTED, cx, panel.y + 34)
            draw_text(self.screen, str(self.score), 64, WHITE, cx, panel.y + 86)
            draw_text(self.screen, f"BEST  {self.best}", 16, YELLOW, cx, panel.y + 140)

            draw_button(self.screen, self.play_btn, "PLAY AGAIN", hover)

        self.draw_camera_overlay()

    def draw_game(self):
        self.background.draw(self.screen)

        # Asteroids
        for a in self.asteroids:
            a.draw(self.screen)

        # Blasts
        for bl in self.blasts:
            bl.draw(self.screen)

        # Bullets
        for b in self.bullets:
            b.draw(self.screen)

        # Rocket
        self.rocket.draw(self.screen)

        # Red flash after losing a life
        if self.hit_flash > 0:
            self.screen.fill((int(70 * self.hit_flash / 14), 0, 0),
                             special_flags=pygame.BLEND_RGB_ADD)
            self.hit_flash -= 1

        self.draw_hud()
        self.draw_camera_overlay()

    def draw_hud(self):
        bar = pygame.Rect(12, 10, WIDTH - 24, 48)
        draw_panel(self.screen, bar)
        mid = bar.centery

        draw_text(self.screen, "SCORE", 14, MUTED, bar.x + 20, mid, anchor="midleft")
        draw_text(self.screen, str(self.score), 26, WHITE, bar.x + 84, mid, anchor="midleft")

        # Gaze indicator: left / center / right segments, the active one lit
        draw_text(self.screen, "GAZE", 14, MUTED, WIDTH // 2 - 96, mid, anchor="midright")
        tracking = self.gaze_dir != "No Face"
        for i, name in enumerate(("Left", "Center", "Right")):
            seg = pygame.Rect(WIDTH // 2 - 84 + i * 58, mid - 12, 52, 24)
            active = self.gaze_dir == name
            lit = YELLOW if name == "Center" else BLUE
            pygame.draw.rect(self.screen, lit if active else (38, 46, 78), seg, border_radius=7)
            if not tracking:
                pygame.draw.rect(self.screen, RED, seg, 1, border_radius=7)
            ink = (14, 18, 34) if active else MUTED
            x, y = seg.center
            if name == "Left":
                pygame.draw.polygon(self.screen, ink, [(x + 5, y - 6), (x + 5, y + 6), (x - 6, y)])
            elif name == "Right":
                pygame.draw.polygon(self.screen, ink, [(x - 5, y - 6), (x - 5, y + 6), (x + 6, y)])
            else:
                pygame.draw.circle(self.screen, ink, (x, y), 5)

        # Lives
        first = bar.right - 20 - START_LIVES * 28
        draw_text(self.screen, "LIVES", 14, MUTED, first - 10, mid, anchor="midright")
        for i in range(START_LIVES):
            heart = self.heart_full if i < self.lives else self.heart_empty
            self.screen.blit(heart, (first + i * 28, mid - 11))

    def draw_camera_overlay(self):
        """Framed live webcam feed in the corner with tracking status."""
        box = pygame.Rect(WIDTH - CAM_W - 22, HEIGHT - CAM_H - 44, CAM_W + 12, CAM_H + 34)
        draw_panel(self.screen, box, radius=10)
        feed = pygame.Rect(box.x + 6, box.y + 6, CAM_W, CAM_H)

        frame = self.tracker.get_frame()
        if frame is not None:
            frame = cv2.cvtColor(cv2.resize(frame, (CAM_W, CAM_H)), cv2.COLOR_BGR2RGB)
            self.screen.blit(pygame.surfarray.make_surface(frame.swapaxes(0, 1)), feed)
        else:
            pygame.draw.rect(self.screen, (12, 15, 28), feed)
            draw_text(self.screen, "NO CAMERA", 14, MUTED, feed.centerx, feed.centery)
        pygame.draw.rect(self.screen, PANEL_EDGE, feed.inflate(2, 2), 1, border_radius=3)

        tracking = self.gaze_dir != "No Face"
        label_y = box.bottom - 14
        pygame.draw.circle(self.screen, GREEN if tracking else RED, (box.x + 14, label_y), 4)
        draw_text(self.screen, "EYE CAM", 12, MUTED, box.x + 25, label_y, anchor="midleft")
        draw_text(self.screen, self.gaze_dir.upper(), 12, WHITE, box.right - 10, label_y,
                  anchor="midright")


# -----------------------------
# Entry point
# -----------------------------

if __name__ == "__main__":
    Game().run()
