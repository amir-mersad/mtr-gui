import pygame
import numpy as np
from math import sin, cos, radians, atan2, degrees

class SkyJetVisualizer:
    def __init__(self, width=800, height=600):
        self.width = width
        self.height = height
        self.screen = pygame.Surface((width, height))
        self.background_color = (135, 206, 235)  # Sky blue
        self.jet_color = (255, 255, 255)  # White
        self.font = pygame.font.Font(None, 24)  # Default font for labels
        
    def resize(self, width, height):
        self.width = width
        self.height = height
        self.screen = pygame.Surface((width, height))

    def draw_jet(self, x, y, angle):
        # Draw a sharper, multi-point jet (F-35-like) pointing in the direction of travel
        # Jet is defined relative to a center (x,y). We'll draw a long nose and swept wings.
        scale = 1.0
        nose = 18 * scale
        tail_w = 6 * scale
        wing_fwd = 8 * scale
        wing_back = -6 * scale
        body_h = 3 * scale

        jet_points = [
            (x - nose * 0.1, y),                 # just behind nose
            (x + nose * 0.8, y),                 # nose tip
            (x + nose * 0.1, y - 2 * body_h),    # upper fuselage
            (x + wing_fwd, y - 3 * body_h),      # forward upper wing
            (x - wing_back, y - 4 * body_h),     # rear upper tail
            (x - nose * 0.6, y - 1 * body_h),    # upper tail curve
            (x - nose * 0.9, y),                 # tail center
            (x - nose * 0.6, y + 1 * body_h),    # lower tail curve
            (x - wing_back, y + 4 * body_h),     # rear lower tail
            (x + wing_fwd, y + 3 * body_h),      # forward lower wing
            (x + nose * 0.1, y + 2 * body_h),    # lower fuselage
        ]
        
        # Rotate the jet based on the angle
        center = (x, y)
        rotated_points = []
        for px, py in jet_points:
            # Translate point to origin
            dx = px - center[0]
            dy = py - center[1]
            # Rotate point
            rx = dx * cos(angle) - dy * sin(angle)
            ry = dx * sin(angle) + dy * cos(angle)
            # Translate back
            rotated_points.append((rx + center[0], ry + center[1]))
        
        # Draw the jet
        pygame.draw.polygon(self.screen, self.jet_color, rotated_points)
        # small nose highlight
        try:
            nose_pt = rotated_points[1]
            pygame.draw.circle(self.screen, (200, 200, 255), (int(nose_pt[0]), int(nose_pt[1])), 2)
        except Exception:
            pass

    def draw_hop(self, hop_data, x, y, text_positions):
        """Draw a hop point already positioned at (x,y). text_positions is a list of rects to avoid collisions."""
        # Draw the hop point
        pygame.draw.circle(self.screen, self.jet_color, (int(x), int(y)), 5)

        # Prepare text
        if hop_data["latency"] == -1:
            latency_text = "Timeout"
        else:
            latency_text = f"{hop_data['latency']:.1f}ms"

        ip_text = self.font.render(f"Hop {hop_data['hop']}: {hop_data['ip']}", True, self.jet_color)
        latency_surface = self.font.render(latency_text, True, self.jet_color)

        # Position text to the right of the point, avoid collisions by shifting down when necessary
        text_x = int(x + 10)
        text_y = int(y - ip_text.get_height() / 2)

        # Clip text horizontally
        if text_x + ip_text.get_width() > self.width - 10:
            text_x = self.width - ip_text.get_width() - 10

        # Avoid overlapping existing text boxes
        rect = pygame.Rect(text_x, text_y, ip_text.get_width(), ip_text.get_height() + 18)
        shift = 0
        while any(rect.colliderect(r) for r in text_positions):
            shift += (self.font.get_height() + 4)
            rect.y = text_y + shift

        # Save rect and blit
        text_positions.append(rect)
        self.screen.blit(ip_text, (rect.x, rect.y))
        self.screen.blit(latency_surface, (rect.x, rect.y + 18))

        return x, y

    def visualize(self, hops):
        self.screen.fill(self.background_color)

        # Keep track of previous coordinates to draw lines and calculate path
        prev_x, prev_y = None, None
        total_hops = len(hops)
        path_points = []

        # Compute latency min/max ignoring timeouts
        latencies = [h["latency"] for h in hops if h.get("latency", -1) >= 0]
        if latencies:
            lat_min = min(latencies)
            lat_max = max(latencies)
        else:
            lat_min = 0.0
            lat_max = 1.0

        top = self.height * 0.1
        bottom = self.height * 0.9
        text_positions = []

        # First pass: compute positions and draw points/text, draw lines
        for i, hop_data in enumerate(hops):
            # horizontal position
            x = (hop_data["hop"] / total_hops) * (self.width - 100) + 50

            # y mapping: highest latency -> top, lowest -> bottom
            if hop_data.get("latency", -1) == -1:
                y = bottom
            else:
                if lat_max == lat_min:
                    norm = 0.5
                else:
                    norm = (hop_data["latency"] - lat_min) / (lat_max - lat_min)
                # invert so high latency -> smaller y (towards top)
                y = top + (1.0 - norm) * (bottom - top)

            path_points.append((x, y))

            # Draw line connecting to previous hop
            if prev_x is not None and prev_y is not None:
                pygame.draw.line(self.screen, self.jet_color, (prev_x, prev_y), (x, y), 2)

            # Draw hop and text, avoid collisions
            self.draw_hop(hop_data, x, y, text_positions)

            prev_x, prev_y = x, y

        # Draw jet at each point with proper angle
        for i in range(len(path_points)):
            x, y = path_points[i]

            # Calculate angle based on next or previous point
            if i < len(path_points) - 1:
                next_x, next_y = path_points[i + 1]
                angle = atan2(next_y - y, next_x - x)
            else:
                # For the last point, fall back to previous segment if available
                if i == 0:
                    angle = 0.0
                else:
                    angle = atan2(y - path_points[i-1][1], x - path_points[i-1][0])

            self.draw_jet(x, y, angle)

        return self.screen