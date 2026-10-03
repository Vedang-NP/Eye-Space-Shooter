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
    - Press P to pause, Q to quit (or ESC).
"""

import random
import sys

import cv2
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

# Gameplay
ROCKET_SPEED = 7
BULLET_SPEED = 12
ASTEROID_SPEED = 3
ASTEROID_SPAWN = 40          # frames between spawns (higher = fewer = easier)
BULLET_COOLDOWN = 12
START_LIVES = 5

# Webcam overlay size (shown in the corner)
CAM_W, CAM_H = 200, 150


# -----------------------------
# Helper functions
# -----------------------------

def draw_text(surface, text, size, color, x, y, center=True):
    font = pygame.font.SysFont("Arial", size, bold=True)
    img = font.render(text, True, color)
    rect = img.get_rect()
    if center:
        rect.center = (x, y)
    else:
        rect.topleft = (x, y)
    surface.blit(img, rect)


def draw_starry_background(surface, stars):
    surface.fill(BLACK)
    for sx, sy, sr in stars:
        pygame.draw.circle(surface, (200, 200, 220), (sx, sy), sr)


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

    def draw(self, surface):
        cx = self.center_x
        top_y = self.y
        # Rocket body (triangle + rectangle)
        body = pygame.Rect(self.x + 10, top_y + 20, self.width - 20, self.height - 20)
        pygame.draw.rect(surface, WHITE, body, border_radius=6)
        pygame.draw.circle(surface, RED, (cx, top_y + 44), 8)      # window
        # Nose cone
        pygame.draw.polygon(
            surface, RED,
            [(self.x + 6, top_y + 20), (self.x + self.width - 6, top_y + 20),
             (cx, top_y)]
        )
        # Fins
        pygame.draw.polygon(
            surface, BLUE,
            [(self.x, top_y + 30), (self.x - 8, top_y + 50), (self.x + 10, top_y + 40)]
        )
        pygame.draw.polygon(
            surface, BLUE,
            [(self.x + self.width, top_y + 30),
             (self.x + self.width + 8, top_y + 50),
             (self.x + self.width - 10, top_y + 40)]
        )
        # Exhaust flame (animated flicker)
        flame = random.randint(8, 16)
        pygame.draw.polygon(
            surface, ORANGE,
            [(cx - 8, top_y + self.height - 8), (cx + 8, top_y + self.height - 8),
             (cx, top_y + self.height + flame)]
        )


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
        pygame.draw.rect(surface, YELLOW, (self.x - self.w // 2, self.y, self.w, self.h), border_radius=3)

    @property
    def rect(self):
        return pygame.Rect(self.x - self.w // 2, self.y, self.w, self.h)


class Asteroid:
    def __init__(self, radius=None):
        self.radius = radius or random.randint(16, 34)
        self.x = random.randint(self.radius, WIDTH - self.radius)
        self.y = -self.radius * 2
        self.speed = random.uniform(ASTEROID_SPEED * 0.6, ASTEROID_SPEED * 1.3)
        self.vert_speed = random.uniform(-0.5, 0.5)
        self.rotation = random.uniform(0, 360)
        self.rot_speed = random.uniform(-2, 2)
        self.vertices = self._make_vertices()

    def _make_vertices(self):
        verts = []
        for i in range(10):
            angle = (i / 10) * 6.28
            r = self.radius * random.uniform(0.7, 1.2)
            vec = pygame.math.Vector2(1, 0).rotate(angle)
            verts.append((r * vec.x, r * vec.y))
        return verts

    def update(self):
        self.y += self.speed
        self.x += self.vert_speed
        self.rotation += self.rot_speed
        if self.x < self.radius or self.x > WIDTH - self.radius:
            self.vert_speed *= -1

    def draw(self, surface):
        points = []
        for vx, vy in self.vertices:
            v = pygame.math.Vector2(vx, vy).rotate(self.rotation)
            points.append((int(self.x + v.x), int(self.y + v.y)))
        pygame.draw.polygon(surface, GRAY, points)
        pygame.draw.polygon(surface, (90, 90, 100), points, 2)

    @property
    def rect(self):
        return pygame.Rect(self.x - self.radius, self.y - self.radius,
                           self.radius * 2, self.radius * 2)


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

        # Stars for background
        self.stars = [(random.randint(0, WIDTH), random.randint(0, HEIGHT),
                       random.randint(1, 3)) for _ in range(120)]

        # Game objects (reset on play)
        self.rocket = Rocket()
        self.bullets = []
        self.asteroids = []
        self.score = 0
        self.lives = START_LIVES
        self.frame_count = 0
        self.shoot_cooldown = 0
        self.gaze_dir = "No Face"

        # Eye tracker (webcam)
        self.tracker = EyeTracker()
        self.tracker.start()

        # Play button rect
        self.play_btn = pygame.Rect(WIDTH // 2 - 100, HEIGHT // 2 + 20, 200, 60)

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
                    if self.state == self.STATE_HOME and self.play_btn.collidepoint(event.pos):
                        self.start_game()
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE or event.key == pygame.K_q:
                        running = False
                    elif event.key == pygame.K_p and self.state == self.STATE_PLAYING:
                        self.state = self.STATE_HOME

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
        self.score = 0
        self.lives = START_LIVES
        self.frame_count = 0
        self.shoot_cooldown = 0
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
                self.lives -= 1
                if self.lives <= 0:
                    self.state = self.STATE_GAME_OVER

        # --- Update asteroids that fell off screen ---
        self.asteroids = [a for a in self.asteroids if a.y < HEIGHT + 60]

    # ----------------------------------------------------------
    # Drawing
    # ----------------------------------------------------------

    def draw_ui(self):
        draw_starry_background(self.screen, self.stars)

        if self.state == self.STATE_HOME:
            draw_text(self.screen, "ROCKET SHOOTER", 64, WHITE, WIDTH // 2, HEIGHT // 2 - 120)
            draw_text(self.screen, "Control your rocket with your EYES!", 28, BLUE,
                      WIDTH // 2, HEIGHT // 2 - 60)
            draw_text(self.screen, "(Look Left / Right to move, Center to shoot)", 22, GRAY,
                      WIDTH // 2, HEIGHT // 2 - 25)
            draw_text(self.screen, "Arrow keys also work as fallback", 20, GRAY,
                      WIDTH // 2, HEIGHT // 2 + 5)

            # Play button
            pygame.draw.rect(self.screen, GREEN, self.play_btn, border_radius=12)
            pygame.draw.rect(self.screen, WHITE, self.play_btn, 3, border_radius=12)
            draw_text(self.screen, "PLAY", 40, BLACK, self.play_btn.centerx, self.play_btn.centery)

            draw_text(self.screen, "Press P to pause anytime", 18, GRAY, WIDTH // 2, HEIGHT - 40)

        elif self.state == self.STATE_GAME_OVER:
            draw_text(self.screen, "GAME OVER", 72, RED, WIDTH // 2, HEIGHT // 2 - 80)
            draw_text(self.screen, f"Final Score: {self.score}", 36, WHITE,
                      WIDTH // 2, HEIGHT // 2 - 10)
            draw_text(self.screen, "Click PLAY to try again", 24, GREEN,
                      WIDTH // 2, HEIGHT // 2 + 40)

            pygame.draw.rect(self.screen, GREEN, self.play_btn, border_radius=12)
            pygame.draw.rect(self.screen, WHITE, self.play_btn, 3, border_radius=12)
            draw_text(self.screen, "PLAY", 40, BLACK, self.play_btn.centerx, self.play_btn.centery)

        self.draw_camera_overlay()

    def draw_game(self):
        draw_starry_background(self.screen, self.stars)

        # Asteroids
        for a in self.asteroids:
            a.draw(self.screen)

        # Bullets
        for b in self.bullets:
            b.draw(self.screen)

        # Rocket
        self.rocket.draw(self.screen)

        # HUD
        draw_text(self.screen, f"Score: {self.score}", 30, WHITE, 90, 30, center=False)
        draw_text(self.screen, f"Lives: {'♥' * self.lives}", 30, RED, WIDTH - 40, 30,
                  center=False)
        draw_text(self.screen, f"Gaze: {self.gaze_dir}", 24, GREEN, WIDTH // 2, 30)

        self.draw_camera_overlay()

    def draw_camera_overlay(self):
        """Draw a small live webcam feed in the corner with the gaze overlay."""
        try:
            ok, frame = self.tracker.cap.read()
            if ok:
                frame = cv2.flip(frame, 1)
                frame = cv2.resize(frame, (CAM_W, CAM_H))
                # Draw gaze direction on the frame
                cv2.putText(frame, self.gaze_dir, (10, 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frame = frame.swapaxes(0, 1)  # rotate for pygame
                surf = pygame.surfarray.make_surface(frame)
                self.screen.blit(surf, (WIDTH - CAM_W - 10, HEIGHT - CAM_H - 10))
        except Exception:
            pass


# -----------------------------
# Entry point
# -----------------------------

if __name__ == "__main__":
    Game().run()
