"""
Module: Neural Memory Defrag Screensaver
Author: Charles-Olivier Dion (AtomikSpace)
Contact: atomikspace.labs@gmail.com
Copyright (c) 2026 Charles-Olivier Dion

This file is authored by Charles-Olivier Dion and is dual-licensed.

Non-Commercial License:
This file is licensed under Creative Commons Attribution-NonCommercial 4.0 International (CC-BY-NC 4.0).
You may use, modify, and redistribute this file for NON-COMMERCIAL purposes only, with attribution.

Commercial License:
Commercial use (including selling products, paid services, SaaS, subscriptions, Patreon rewards, or derivatives)
requires a separate written license from Charles-Olivier Dion (AtomikSpace).

This license applies only to this file and does not override licenses of other files in the repository.
"""
import pygame
import random
import time
from UI.module_screensaver_overlay import TimeOverlay


class DefragAnimation:
    TYPE_FREE = 0
    TYPE_FRAGMENTED = 1
    TYPE_USED = 2
    TYPE_OPTIMIZED = 3
    TYPE_BAD = -1
    
    COLORS = {
        'background': (60, 60, 180),
        'text': (220, 220, 220),
        'text_highlight': (220, 220, 60),
        'used': (220, 220, 220),
        'fragmented': (140, 140, 140),
        'optimized': (220, 220, 60),
        'free': (70, 70, 200),
        'reading': (220, 60, 60),
        'writing': (60, 220, 60),
        'panel_border': (220, 220, 220),
        'black': (0, 0, 0),
        'bar_bg': (255, 255, 255),
        'bar_text': (0, 0, 0),
    }
    
    BORDER_HEIGHT = 100
    BAR_HEIGHT = 30
    
    def __init__(self, screen, width, height, show_time=False):
        self.screen = screen
        self.width = width
        self.height = height
        
        self.show_time = show_time
        self.time_overlay = TimeOverlay(width, height) if show_time else None
        
        self.block_size = 14
        self.block_gap = 2
        self.cell_size = self.block_size + self.block_gap
        
        self.margin_x = 20
        self.content_top = self.BORDER_HEIGHT + self.BAR_HEIGHT + 10
        self.content_bottom = self.height - self.BORDER_HEIGHT - self.BAR_HEIGHT
        self.panel_height = 130
        self.grid_width = (width - 2 * self.margin_x) // self.cell_size
        self.grid_height = (self.content_bottom - self.content_top - self.panel_height - 20) // self.cell_size
        
        self.total_blocks = self.grid_width * self.grid_height
        self.grid = []
        
        self.phase = 'defragmenting'
        self.start_time = time.time()
        self.complete_time = None
        self.countdown = 10
        
        self.move_state = 'idle'
        self.move_timer = 0
        self.move_sources = []
        self.move_dests = []
        self.read_duration = 5
        self.write_duration = 4
        
        self.work_area = None
        
        self.font = None
        self.font_small = None
        self._init_fonts()
        
        self.neural_messages = [
            "Consolidating episodic memories...",
            "Optimizing synaptic pathways...",
            "Reorganizing semantic clusters...",
            "Strengthening neural connections...",
            "Compacting working memory...",
            "Indexing long-term storage...",
            "Defragmenting neural patterns...",
            "Synchronizing memory engrams...",
        ]
        self.current_message = random.choice(self.neural_messages)
        self.message_timer = 0
        self.message_interval = 5
        
        self.block_freshness = {}
        
        self._initialize_disk()
    
    def _init_fonts(self):
        import os
        script_dir = os.path.dirname(os.path.abspath(__file__))
        font_path = os.path.join(script_dir, 'vga.ttf')
        
        try:
            if os.path.exists(font_path):
                self.font = pygame.font.Font(font_path, 20)
                self.font_small = pygame.font.Font(font_path, 16)
            else:
                self.font = pygame.font.Font(None, 22)
                self.font_small = pygame.font.Font(None, 18)
        except:
            self.font = pygame.font.Font(None, 22)
            self.font_small = pygame.font.Font(None, 18)
    
    def _initialize_disk(self):
        self.grid = [self.TYPE_FREE] * self.total_blocks
        
        top_rows = random.randint(3, 5)
        top_end = top_rows * self.grid_width
        
        num_bad = max(2, int(self.total_blocks * 0.002))
        bad_positions = random.sample(range(top_end, self.total_blocks), num_bad)
        for pos in bad_positions:
            self.grid[pos] = self.TYPE_BAD
        
        for i in range(0, top_end):
            if self.grid[i] == self.TYPE_FREE:
                if random.random() < 0.65:
                    self.grid[i] = self.TYPE_USED
        
        num_near_clusters = random.randint(2, 5)
        for _ in range(num_near_clusters):
            if random.random() < 0.5:
                gap = self.grid_width
            else:
                gap = random.randint(10, 30)
            
            start_pos = top_end + gap
            cluster_size = random.randint(3, 8)
            
            for j in range(cluster_size):
                pos = start_pos + j
                if pos < self.total_blocks and self.grid[pos] == self.TYPE_FREE:
                    self.grid[pos] = self.TYPE_USED
        
        available = [i for i in range(top_end, self.total_blocks) if self.grid[i] == self.TYPE_FREE]
        total_fragmented = int(len(available) * 0.52)
        
        placed = 0
        while placed < total_fragmented and available:
            center = random.choice(available)
            cluster_size = random.randint(2, 8)
            
            for _ in range(cluster_size):
                if placed >= total_fragmented:
                    break
                dx = random.randint(-3, 3)
                dy = random.randint(-1, 1)
                pos = center + dx + dy * self.grid_width
                if pos in available and pos >= top_end:
                    self.grid[pos] = self.TYPE_FRAGMENTED
                    available.remove(pos)
                    placed += 1
    
    def _get_block_position(self, index):
        col = index % self.grid_width
        row = index // self.grid_width
        x = self.margin_x + col * self.cell_size
        y = self.content_top + row * self.cell_size
        return x, y
    
    def reset(self):
        self.phase = 'defragmenting'
        self.start_time = time.time()
        self.complete_time = None
        self.countdown = 10
        self.move_state = 'idle'
        self.move_timer = 0
        self.move_sources = []
        self.move_dests = []
        self.work_area = None
        self.current_message = random.choice(self.neural_messages)
        self.message_timer = 0
        self.block_freshness = {}
        self._initialize_disk()
    
    def update(self):
        if self.phase == 'defragmenting':
            self._update_defrag()
            
        elif self.phase == 'complete':
            if self.complete_time is None:
                self.complete_time = time.time()
            elapsed = time.time() - self.complete_time
            self.countdown = max(0, 10 - int(elapsed))
            if self.countdown <= 0:
                self.reset()
    
    def _update_defrag(self):
        self.message_timer += 1
        if self.message_timer >= self.message_interval:
            self.message_timer = 0
            self.current_message = random.choice(self.neural_messages)
        
        if self.move_state == 'idle':
            move = self._find_next_move()
            
            if move is None:
                self._update_optimized()
                self.phase = 'complete'
                self.current_message = "Memory consolidation complete!"
                return
            
            self.move_sources, self.move_dests = move
            self.move_state = 'reading'
            self.move_timer = 0
        
        elif self.move_state == 'reading':
            self.move_timer += 1
            if self.move_timer >= self.read_duration:
                self.move_state = 'writing'
                self.move_timer = 0
        
        elif self.move_state == 'writing':
            self.move_timer += 1
            if self.move_timer >= self.write_duration:
                to_remove = []
                for pos in self.block_freshness:
                    self.block_freshness[pos] -= 1
                    if self.block_freshness[pos] <= 0:
                        to_remove.append(pos)
                for pos in to_remove:
                    del self.block_freshness[pos]
                
                for src, dst in zip(self.move_sources, self.move_dests):
                    self.grid[dst] = self.TYPE_FRAGMENTED
                    self.grid[src] = self.TYPE_FREE
                    self.block_freshness[dst] = 10
                
                self._update_optimized()
                
                self.move_sources = []
                self.move_dests = []
                self.move_state = 'idle'
    
    def _update_optimized(self):
        for i in range(self.total_blocks):
            if self.grid[i] == self.TYPE_FREE:
                break
            elif self.grid[i] == self.TYPE_FRAGMENTED:
                self.grid[i] = self.TYPE_OPTIMIZED
            elif self.grid[i] == self.TYPE_USED:
                self.grid[i] = self.TYPE_OPTIMIZED
    
    def _find_next_move(self):
        gaps = []
        for i in range(self.total_blocks):
            if self.grid[i] == self.TYPE_FREE:
                gaps.append(i)
        
        if not gaps:
            return None
        
        frags = [i for i in range(self.total_blocks) if self.grid[i] == self.TYPE_FRAGMENTED]
        if not frags:
            return None
        
        if random.random() < 0.10:
            gaps_between_completed = []
            for g in gaps:
                has_completed_before = False
                has_completed_after = False
                for j in range(g - 1, max(0, g - 10), -1):
                    if self.grid[j] in [self.TYPE_USED, self.TYPE_OPTIMIZED]:
                        has_completed_before = True
                        break
                    elif self.grid[j] == self.TYPE_FRAGMENTED:
                        break
                for j in range(g + 1, min(self.total_blocks, g + 10)):
                    if self.grid[j] in [self.TYPE_USED, self.TYPE_OPTIMIZED]:
                        has_completed_after = True
                        break
                    elif self.grid[j] == self.TYPE_FRAGMENTED:
                        break
                if has_completed_before and has_completed_after:
                    gaps_between_completed.append(g)
            
            if gaps_between_completed and random.random() < 0.7:
                gap_start = random.choice(gaps_between_completed)
            else:
                gap_start = gaps[min(len(gaps)-1, random.randint(0, 3))]
        else:
            gaps_near_gray = []
            for g in gaps:
                for offset in [-1, 1, -self.grid_width, self.grid_width]:
                    neighbor = g + offset
                    if 0 <= neighbor < self.total_blocks and self.grid[neighbor] == self.TYPE_FRAGMENTED:
                        gaps_near_gray.append(g)
                        break
            
            if gaps_near_gray:
                gaps_near_gray.sort()
                top_half = gaps_near_gray[:max(1, len(gaps_near_gray)//2)]
                gap_start = random.choice(top_half)
            else:
                gap_start = gaps[min(len(gaps)-1, random.randint(0, 2))]
        
        free_count = 1
        for i in range(gap_start + 1, self.total_blocks):
            if self.grid[i] == self.TYPE_FREE:
                free_count += 1
            else:
                break
        
        batch_size = min(random.randint(2, 8), free_count)
        
        if not self.work_area or random.random() < 0.25:
            frags_sorted = sorted(frags)
            lower_half = frags_sorted[len(frags_sorted)//2:]
            self.work_area = random.choice(lower_half) if lower_half else random.choice(frags)
        
        work_row = self.work_area // self.grid_width
        row_start = work_row * self.grid_width
        row_end = row_start + self.grid_width
        
        row_frags = [i for i in range(max(0, row_start - self.grid_width), 
                                       min(self.total_blocks, row_end + self.grid_width))
                     if self.grid[i] == self.TYPE_FRAGMENTED]
        
        if not row_frags:
            row_frags = frags
            self.work_area = random.choice(frags)
        
        sources = []
        row_frags.sort()
        
        if row_frags:
            start_idx = random.randint(0, len(row_frags) - 1)
            sources.append(row_frags[start_idx])
            
            last_pos = row_frags[start_idx]
            for idx in range(start_idx + 1, len(row_frags)):
                pos = row_frags[idx]
                if pos - last_pos <= 3:
                    sources.append(pos)
                    last_pos = pos
                    if len(sources) >= batch_size:
                        break
                else:
                    break
            
            if len(sources) < batch_size:
                first_pos = sources[0]
                for idx in range(start_idx - 1, -1, -1):
                    pos = row_frags[idx]
                    if first_pos - pos <= 3:
                        sources.insert(0, pos)
                        first_pos = pos
                        if len(sources) >= batch_size:
                            break
                    else:
                        break
        
        if sources:
            sources.sort()
            dests = list(range(gap_start, gap_start + len(sources)))
            self.work_area = sources[len(sources)//2]
            return (sources, dests)
        
        return None
    
    def render(self):
        self.screen.fill(self.COLORS['background'])
        
        self._draw_borders()
        self._draw_top_bar()
        self._draw_bottom_bar()
        self._draw_memory_grid()
        self._draw_bottom_panel()
        
        if self.phase == 'complete':
            self._draw_complete_popup()
        
        if self.show_time and self.time_overlay:
            self.time_overlay.render(self.screen)
    
    def _draw_borders(self):
        pygame.draw.rect(self.screen, self.COLORS['black'], (0, 0, self.width, self.BORDER_HEIGHT))
        pygame.draw.rect(self.screen, self.COLORS['black'], (0, self.height - self.BORDER_HEIGHT, self.width, self.BORDER_HEIGHT))
    
    def _draw_top_bar(self):
        bar_y = self.BORDER_HEIGHT
        pygame.draw.rect(self.screen, self.COLORS['bar_bg'], (0, bar_y, self.width, self.BAR_HEIGHT))
        text = self.font.render("DEFRAGMENTATION", True, self.COLORS['bar_text'])
        self.screen.blit(text, (self.margin_x, bar_y + (self.BAR_HEIGHT - text.get_height()) // 2))
    
    def _draw_bottom_bar(self):
        bar_y = self.height - self.BORDER_HEIGHT - self.BAR_HEIGHT
        pygame.draw.rect(self.screen, self.COLORS['bar_bg'], (0, bar_y, self.width, self.BAR_HEIGHT))
        
        msg_text = self.font.render(self.current_message, True, self.COLORS['reading'])
        self.screen.blit(msg_text, (self.margin_x, bar_y + (self.BAR_HEIGHT - msg_text.get_height()) // 2))
        
        text = self.font.render("TARS O.S.", True, self.COLORS['bar_text'])
        self.screen.blit(text, (self.width - self.margin_x - text.get_width(), bar_y + (self.BAR_HEIGHT - text.get_height()) // 2))
    
    def _draw_complete_popup(self):
        popup_w = 350
        popup_h = 120
        popup_x = (self.width - popup_w) // 2
        popup_y = (self.height - popup_h) // 2
        
        pygame.draw.rect(self.screen, (192, 192, 192), (popup_x, popup_y, popup_w, popup_h))
        pygame.draw.rect(self.screen, (255, 255, 255), (popup_x, popup_y, popup_w - 2, popup_h - 2), 2)
        pygame.draw.rect(self.screen, (128, 128, 128), (popup_x + 2, popup_y + 2, popup_w - 2, popup_h - 2), 2)
        pygame.draw.rect(self.screen, (0, 0, 0), (popup_x, popup_y, popup_w, popup_h), 1)
        
        title = self.font.render("Completed", True, (0, 0, 0))
        title_x = popup_x + (popup_w - title.get_width()) // 2
        self.screen.blit(title, (title_x, popup_y + 15))
        
        msg = self.font_small.render("Memory consolidation complete!", True, (0, 0, 0))
        msg_x = popup_x + (popup_w - msg.get_width()) // 2
        self.screen.blit(msg, (msg_x, popup_y + 45))
        
        countdown_text = self.font_small.render(f"Next neural net in {self.countdown} seconds...", True, (0, 0, 0))
        countdown_x = popup_x + (popup_w - countdown_text.get_width()) // 2
        self.screen.blit(countdown_text, (countdown_x, popup_y + 70))
        
        btn_w, btn_h = 60, 22
        btn_x = popup_x + (popup_w - btn_w) // 2
        btn_y = popup_y + popup_h - btn_h - 10
        pygame.draw.rect(self.screen, (192, 192, 192), (btn_x, btn_y, btn_w, btn_h))
        pygame.draw.rect(self.screen, (255, 255, 255), (btn_x, btn_y, btn_w - 1, btn_h - 1), 1)
        pygame.draw.rect(self.screen, (128, 128, 128), (btn_x + 1, btn_y + 1, btn_w - 1, btn_h - 1), 1)
        ok_text = self.font_small.render("OK", True, (0, 0, 0))
        self.screen.blit(ok_text, (btn_x + (btn_w - ok_text.get_width()) // 2, btn_y + 3))
    
    def _draw_memory_grid(self):
        for i in range(self.total_blocks):
            x, y = self._get_block_position(i)
            block_type = self.grid[i]
            
            is_reading = (self.move_state == 'reading' and i in self.move_sources)
            is_writing = (self.move_state == 'writing' and i in self.move_dests)
            freshness = self.block_freshness.get(i, 0)
            
            self._draw_block(x, y, block_type, is_reading, is_writing, freshness)
    
    def _draw_block(self, x, y, block_type, is_reading=False, is_writing=False, freshness=0):
        size = self.block_size
        
        if is_reading:
            pygame.draw.rect(self.screen, self.COLORS['reading'], (x, y, size, size))
            letter = self.font_small.render("R", True, self.COLORS['background'])
            self.screen.blit(letter, (x + 2, y + 0))
        
        elif is_writing:
            pygame.draw.rect(self.screen, self.COLORS['writing'], (x, y, size, size))
            letter = self.font_small.render("W", True, self.COLORS['background'])
            self.screen.blit(letter, (x + 1, y + 0))
        
        elif block_type == self.TYPE_FREE:
            pygame.draw.rect(self.screen, self.COLORS['free'], (x, y, size, size))
        
        elif block_type == self.TYPE_BAD:
            letter = self.font_small.render("X", True, self.COLORS['text'])
            self.screen.blit(letter, (x + 2, y + 0))
        
        elif block_type == self.TYPE_FRAGMENTED:
            if freshness > 0:
                base = self.COLORS['fragmented']
                bright = (180, 180, 180)
                t = freshness / 10.0
                color = (
                    int(base[0] + (bright[0] - base[0]) * t),
                    int(base[1] + (bright[1] - base[1]) * t),
                    int(base[2] + (bright[2] - base[2]) * t)
                )
                pygame.draw.rect(self.screen, color, (x, y, size, size))
            else:
                pygame.draw.rect(self.screen, self.COLORS['fragmented'], (x, y, size, size))
        
        elif block_type == self.TYPE_USED:
            pygame.draw.rect(self.screen, self.COLORS['used'], (x, y, size, size))
            dot_size = 3
            pygame.draw.rect(self.screen, self.COLORS['background'], 
                           (x + size//2 - dot_size//2, y + size//2 - dot_size//2, 
                            dot_size, dot_size))
        
        elif block_type == self.TYPE_OPTIMIZED:
            pygame.draw.rect(self.screen, self.COLORS['optimized'], (x, y, size, size))
            dot_size = 3
            pygame.draw.rect(self.screen, self.COLORS['background'], 
                           (x + size//2 - dot_size//2, y + size//2 - dot_size//2, 
                            dot_size, dot_size))
    
    def _draw_bottom_panel(self):
        panel_y = self.content_bottom - self.panel_height - 10
        panel_width = (self.width - 3 * self.margin_x) // 2
        
        self._draw_panel_box(self.margin_x, panel_y, panel_width, self.panel_height, "Status")
        self._draw_status_content(self.margin_x + 10, panel_y + 25, panel_width - 20)
        
        legend_x = self.margin_x * 2 + panel_width
        self._draw_panel_box(legend_x, panel_y, panel_width, self.panel_height, "Legend")
        self._draw_legend_content(legend_x + 10, panel_y + 25, panel_width - 20)
    
    def _draw_panel_box(self, x, y, w, h, title):
        pygame.draw.rect(self.screen, self.COLORS['panel_border'], (x, y, w, h), 1)
        
        title_surface = self.font.render(f" {title} ", True, self.COLORS['text_highlight'])
        title_x = x + (w - title_surface.get_width()) // 2
        
        pygame.draw.rect(self.screen, self.COLORS['background'], 
                        (title_x - 2, y - 2, title_surface.get_width() + 4, 4))
        self.screen.blit(title_surface, (title_x, y - 8))
    
    def _draw_status_content(self, x, y, w):
        if self.phase == 'defragmenting':
            optimized = sum(1 for b in self.grid if b == self.TYPE_OPTIMIZED)
            total_data = sum(1 for b in self.grid if b in [self.TYPE_OPTIMIZED, self.TYPE_USED, self.TYPE_FRAGMENTED])
            
            if total_data > 0:
                pct = int((optimized / total_data) * 100)
            else:
                pct = 100
        else:
            pct = 100
        
        cluster_num = self.move_sources[0] if self.move_sources else 0
        cluster_text = f"Cluster {cluster_num:,}"
        text = self.font.render(cluster_text, True, self.COLORS['text'])
        self.screen.blit(text, (x, y))
        
        pct_text = f"{pct}%"
        pct_surface = self.font.render(pct_text, True, self.COLORS['text'])
        self.screen.blit(pct_surface, (x + w - pct_surface.get_width() - 10, y))
        
        bar_y = y + 25
        bar_width = w - 20
        bar_height = 16
        
        pygame.draw.rect(self.screen, self.COLORS['text'], (x, bar_y, bar_width, bar_height), 1)
        
        fill_width = int((bar_width - 4) * (pct / 100))
        if fill_width > 0:
            pygame.draw.rect(self.screen, self.COLORS['text'], 
                           (x + 2, bar_y + 2, fill_width, bar_height - 4))
        
        elapsed = time.time() - self.start_time
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)
        time_str = f"Elapsed Time: {hours:02d}:{minutes:02d}:{seconds:02d}"
        time_text = self.font.render(time_str, True, self.COLORS['text'])
        self.screen.blit(time_text, (x + (w - time_text.get_width()) // 2, bar_y + 25))
        
        if self.phase == 'defragmenting':
            if self.move_state == 'reading':
                op_text = "Reading..."
            elif self.move_state == 'writing':
                op_text = "Writing..."
            else:
                op_text = "Full Optimization"
        else:
            op_text = "Complete"
        
        op_surface = self.font.render(op_text, True, self.COLORS['text'])
        self.screen.blit(op_surface, (x + (w - op_surface.get_width()) // 2, bar_y + 45))
    
    def _draw_legend_content(self, x, y, w):
        items = [
            (self.COLORS['used'], "o", "Used", self.COLORS['free'], ":", "Unused"),
            (self.COLORS['reading'], "R", "Reading", self.COLORS['writing'], "W", "Writing"),
            (self.COLORS['optimized'], "o", "Optimized", self.COLORS['text'], "X", "Bad"),
        ]
        
        line_height = 22
        col_width = w // 2
        
        for i, (left_color, left_sym, left_label, right_color, right_sym, right_label) in enumerate(items):
            cy = y + i * line_height
            
            sym_surface = self.font.render(left_sym, True, left_color)
            self.screen.blit(sym_surface, (x, cy))
            label_surface = self.font.render(f" - {left_label}", True, self.COLORS['text'])
            self.screen.blit(label_surface, (x + sym_surface.get_width(), cy))
            
            sym_surface = self.font.render(right_sym, True, right_color)
            self.screen.blit(sym_surface, (x + col_width, cy))
            label_surface = self.font.render(f" - {right_label}", True, self.COLORS['text'])
            self.screen.blit(label_surface, (x + col_width + sym_surface.get_width(), cy))
        
        info_y = y + len(items) * line_height + 8
        info_text = f"Neural Net: 1 block = {random.randint(8, 16)} engrams"
        info_surface = self.font_small.render(info_text, True, self.COLORS['text'])
        self.screen.blit(info_surface, (x, info_y))
    
    def cleanup(self):
        pass