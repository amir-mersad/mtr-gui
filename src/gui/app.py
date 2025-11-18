import tkinter as tk
from tkinter import ttk
import pygame
import time
import os
import sys
from network.mtr import MTRTracer
import threading
from visualization.sky_jet import SkyJetVisualizer

class MTRApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MTR Network Visualizer")
        
        # Initialize pygame
        pygame.init()
        
        # Create GUI elements
        self.create_gui()
        # Initialize visualizer
        self.visualizer = SkyJetVisualizer()
        # Last visualization surface for standalone pygame window
        self._last_viz_surface = None
        # Auto-trace scheduling id
        self.auto_after_id = None
        # Start automatic tracing shortly after GUI is ready
        try:
            self.root.after(100, self.start_and_schedule)
        except Exception:
            pass
        # Thread handle for background trace
        self._trace_thread = None

    def start_and_schedule(self):
        # Run an initial trace (non-blocking) and let _on_trace_complete schedule the next
        try:
            self.start_trace()
        except Exception as e:
            print(f"[debug] initial start_trace failed: {e}")
        
    def create_gui(self):
        # Target input frame
        input_frame = ttk.Frame(self.root)
        input_frame.pack(padx=10, pady=5, fill=tk.X)
        
        ttk.Label(input_frame, text="Target:").pack(side=tk.LEFT)
        self.target_entry = ttk.Entry(input_frame)
        self.target_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.target_entry.insert(0, "8.8.8.8")  # Default target
        
        ttk.Button(input_frame, text="Trace", command=self.start_trace).pack(side=tk.LEFT)
        
        # Create pygame embed frame
        self.embed = tk.Frame(self.root, width=800, height=600)
        self.embed.pack(expand=True, fill=tk.BOTH)

        # On Windows SDL_WINDOWID embedding is unreliable. Fall back to a standalone pygame window.
        if sys.platform.startswith("win"):
            print("[debug] running in standalone pygame window on Windows (embedding not supported)")
            self.embedded = False
            # create a normal pygame window
            self.screen = pygame.display.set_mode((800, 600))
            pygame.display.set_caption("MTR Visualization - Pygame Window")
            # Hide the Tk window to avoid showing two windows; keep mainloop running for scheduling
            try:
                self.root.withdraw()
                print("[debug] Tk window withdrawn; using standalone Pygame window only")
            except Exception:
                pass
            # start periodic pump to keep the pygame window updated
            self.root.after(50, self._pyg_loop)
        else:
            # Ensure the Tk widget is realized so winfo_id() returns a valid window handle
            self.root.update_idletasks()
            self.root.update()

            # Tell pygame's SDL window which window ID to use
            os.environ['SDL_WINDOWID'] = str(self.embed.winfo_id())

            # Set up the pygame display embedded into the Tk frame
            self.embedded = True
            self.screen = pygame.display.set_mode((800, 600))
            print(f"[debug] embedding pygame into Tkinter widget id={self.embed.winfo_id()}")
        
    def start_trace(self):
        # Non-blocking: start tracer in a background thread and return
        if self._trace_thread and self._trace_thread.is_alive():
            print("[debug] trace already running, skipping new trace")
            return

        target = self.target_entry.get()

        def worker(tgt):
            try:
                tracer = MTRTracer(tgt)
                hops = tracer.trace()
            except Exception as e:
                print(f"[debug] tracer thread error: {e}")
                hops = []
            # schedule completion handler in main thread
            try:
                self.root.after(0, lambda: self._on_trace_complete(hops))
            except Exception as e:
                print(f"[debug] failed to schedule _on_trace_complete: {e}")

        self._trace_thread = threading.Thread(target=worker, args=(target,), daemon=True)
        self._trace_thread.start()

    def _on_trace_complete(self, hops):
        # This runs in the main thread (scheduled via root.after)
        print(f"[debug] got {len(hops)} hops")
        for h in hops:
            print(f"[debug] hop {h.get('hop')} {h.get('ip')} {h.get('latency')}")

        # Determine target drawing size depending on embedded or standalone
        if getattr(self, 'embedded', False):
            width = max(100, self.embed.winfo_width())
            height = max(100, self.embed.winfo_height())
        else:
            width, height = self.screen.get_size()
        # Resize visualizer surface if needed
        if (width, height) != (self.visualizer.width, self.visualizer.height):
            self.visualizer.resize(width, height)

        # Clear the screen
        self.screen.fill((135, 206, 235))  # Sky blue background

        # Update visualization
        viz_surface = self.visualizer.visualize(hops)

        # Copy visualization to screen
        try:
            self.screen.blit(viz_surface, (0, 0))
        except Exception:
            # If blit fails (size mismatch), create a surface fit
            try:
                viz_surface = pygame.transform.scale(viz_surface, self.screen.get_size())
                self.screen.blit(viz_surface, (0, 0))
            except Exception as e:
                print(f"[debug] blit/scale failed: {e}")

        # Save last viz for periodic redraw (standalone mode)
        self._last_viz_surface = viz_surface

        # Update the display
        pygame.display.flip()
        # Debug info: sizes
        try:
            print(f"[debug] screen size: {self.screen.get_size()}, viz size: {viz_surface.get_size()}")
        except Exception:
            print("[debug] could not read surface sizes")

        # Pump events briefly so OS updates the window and allow rendering
        try:
            for _ in range(30):
                pygame.event.pump()
                time.sleep(0.01)
        except Exception as e:
            print(f"[debug] pygame event pump error: {e}")

        # Save screenshot for debugging
        try:
            screenshot_path = os.path.join(os.getcwd(), "last_trace.png")
            pygame.image.save(self.screen, screenshot_path)
            print(f"[debug] saved screenshot to {screenshot_path}")
        except Exception as e:
            print(f"[debug] screenshot save failed: {e}")

        # schedule next trace after a fixed interval
        self.schedule_next_trace()

    def schedule_next_trace(self, delay_ms=15000):
        """Schedule the next automatic trace in delay_ms milliseconds."""
        try:
            if self.auto_after_id is not None:
                self.root.after_cancel(self.auto_after_id)
        except Exception:
            pass
        try:
            self.auto_after_id = self.root.after(delay_ms, self._auto_trace)
        except Exception as e:
            print(f"[debug] schedule_next_trace failed: {e}")

    def cancel_scheduled_trace(self):
        if self.auto_after_id is not None:
            try:
                self.root.after_cancel(self.auto_after_id)
            except Exception:
                pass
            self.auto_after_id = None

    def _auto_trace(self):
        # Automatic trace called by Tk scheduler
        try:
            self.start_trace()
        except Exception as e:
            print(f"[debug] auto trace failed: {e}")
        finally:
            # schedule next run
            self.schedule_next_trace()

    def _pyg_loop(self):
        """Periodic pump/redraw for standalone pygame window. Called from Tk mainloop via after()."""
        try:
            # pump events
            pygame.event.pump()
            # redraw last visualization if present
            if self._last_viz_surface is not None:
                try:
                    # scale if necessary
                    if self._last_viz_surface.get_size() != self.screen.get_size():
                        surf = pygame.transform.scale(self._last_viz_surface, self.screen.get_size())
                    else:
                        surf = self._last_viz_surface
                    self.screen.blit(surf, (0, 0))
                    pygame.display.flip()
                except Exception as e:
                    print(f"[debug] periodic blit failed: {e}")
        except Exception as e:
            print(f"[debug] pyg loop error: {e}")
        # schedule next call
        try:
            self.root.after(50, self._pyg_loop)
        except Exception:
            pass

def main():
    root = tk.Tk()
    app = MTRApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()