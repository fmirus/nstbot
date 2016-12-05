from . import nstbot
import numpy as np
import threading
import time


class OmniArmBot(nstbot.NSTBot):
    def initialize(self):
        super(OmniArmBot, self).initialize()
        self.retina(False)
        self.retina_packet_size = None
        self.image = None
        self.count_spike_regions = None
        self.track_periods = None
        self.sensor = {}
        self.sensor_scale = {}
        self.sensor_map = {}
        self.add_sensor('bump', bit=0, range=1, length=1)
        self.add_sensor('wheel', bit=1, range=100, length=8) # we take only the first 3 vals (base motors)
        # the hex encoded values need conversion
        self.add_sensor('gyro', bit=2, range=2**32-1, length=4) # we take only the first 3 vals (x, y, z)
        self.add_sensor('accel', bit=3, range=2**32-1, length=3)
        self.add_sensor('euler', bit=4, range=2**32-1, length=4) # we take only the first 3 vals (x, y, z)
        self.add_sensor('compass', bit=5, range=2**32-1, length=3)
        self.add_sensor('servo', bit=7, range=4096, length=8) # we only take the last 5 (arm motors)
        self.add_sensor('load', bit=9, range=4096, length=8)# we only take the last 5 (arm motors)
        # self.sensor_bitmap = {"wheel": [17,slice(0, 3)], "gyro": [4,slice(0, 3)], "accel": [5, slice(0,3)], "euler": [9, slice(0,3)], "compass": [6, slice(0, 3)], "servo": [16, slice(4, 8)], "load": [14, slice(4, 8)]}
        self.sensor_bitmap = {"bump": [19, slice(0, 1)],
                              "wheel": [17,slice(0, 3)],
                              "gyro": [4,slice(0, 3)],
                              "accel": [5, slice(0,3)],
                              "euler": [9, slice(0,3)],
                              "compass": [6, slice(0, 3)],
                              "servo": [16, slice(3, 8)],
                              "load": [14, slice(3, 8)]}
        self.motor(0, 0, 0)
        #self.arm(0.184, 0.172, 0.394, 0.052, 0.134)

    def motor(self, x, y, rot, msg_period=None):
        vrange = 100
        x = int(x * vrange)
        y = int(y * vrange)
        rot = int(rot * vrange)

        if x > vrange: x = vrange
        if x < -vrange: x = -vrange
        if y > vrange: y = vrange
        if y < -vrange: y = -vrange
        if rot > vrange: rot = vrange
        if rot < -vrange: rot = -vrange
        cmd = '!D%d,%d,%d\n' % (x, y, rot)
        self.send('motor', cmd, msg_period=msg_period)

    def arm(self, j1, j2, j3, j4, j5, msg_period=None):

        # motion should be limited by the dynamics of the robot
        # min pos and max pos in the range
        vrange = 4096
        min_pos = np.array([630, 250, 1100, 0, 550])
        max_pos = np.array([2700, 2700, 3000, 600, 1000])

        joints = (np.array([j1, j2, j3, j4, j5]) * vrange).astype(dtype=np.int)

        # apply limits
        joints[joints < min_pos] = min_pos[joints < min_pos]
        joints[joints > max_pos] = max_pos[joints > max_pos]

        # indices for motor IDs
        for ids in range(3, 8, 1):
            cmd = '!G%d%d\n' % (ids, joints[ids - 3])
            self.send('arm%d' % ids, cmd, msg_period=msg_period)

    def add_sensor(self, name, bit, range, length):
        value = np.zeros(length)
        self.sensor[bit] = value
        self.sensor[name] = value
        self.sensor_map[bit] = name
        self.sensor_map[name] = bit
        self.sensor_scale[bit] = 1.0 / range

    def activate_sensors(self, period=0.1, **names):
        bits = 0
        for name in names:
            bit = self.sensor_map[name]
            bits += 1 << bit
        cmd = '!I1,%d,%d\n' % (int(1.0/period), bits)
        self.connection.send(cmd)

    def get_sensor(self, name):
        return self.sensor[name]

    def connect(self, connection):
        super(OmniArmBot, self).connect(connection)
        # self.connection.send('!E2\n')
        # time.sleep(1)
        thread = threading.Thread(target=self.sensor_loop)
        thread.daemon = True
        thread.start()

    def disconnect(self):
        self.retina(False)
        self.connection.send('!I0\n')
        self.motor(0, 0, 0)
        # self.arm(0.184, 0.172, 0.394, 0.052, 0.134)
        super(OmniArmBot, self).disconnect()

    def retina(self, active, bytes_in_timestamp=4):
        if active:
            assert bytes_in_timestamp in [0, 2, 3, 4]
            cmd = '!E%d\nE+\n' % bytes_in_timestamp
            self.retina_packet_size = 2 + bytes_in_timestamp
        else:
            cmd = 'E-\n'
            self.retina_packet_size = None
        self.connection.send(cmd)

    def show_image(self, decay=0.5, display_mode='quick'):
        if self.image is None:
            self.image = np.zeros((128, 128), dtype=float)
            thread = threading.Thread(target=self.image_loop,
                                      args=(decay, display_mode))
            thread.daemon = True
            thread.start()

    def keep_image(self):
        if self.image is None:
            self.image = np.zeros((128, 128), dtype=float)


    def image_loop(self, decay, display_mode):
        import pylab

        import matplotlib.pyplot as plt
        # using axis for updating only parts of the image that change
        fig, ax = plt.subplots()
        # so quick mode can run on ubuntu
        plt.show(block=False)

        pylab.ion()
        img = pylab.imshow(self.image, vmax=1, vmin=-1,
                                       interpolation='none', cmap='binary')
        pylab.xlim(0, 127)
        pylab.ylim(127, 0)

        regions = {}
        if self.count_spike_regions is not None:
            for k, v in self.count_spike_regions.items():
                minx, miny, maxx, maxy = v
                rect = pylab.Rectangle((minx - 0.5, miny - 0.5),
                                       maxx - minx,
                                       maxy - miny,
                                       facecolor='yellow', alpha=0.2)
                pylab.gca().add_patch(rect)
                regions[k] = rect

        if self.track_periods is not None:
            colors = ([(0,0,1), (0,1,0), (1,0,0), (1,1,0), (1,0,1)] * 10)[:len(self.p_y)]
            scatter = pylab.scatter(self.p_x, self.p_y, s=50, c=colors)
        else:
            scatter = None

        while True:

            img.set_data(self.image)

            for k, rect in regions.items():
                alpha = self.get_spike_rate(k) * 0.5
                alpha = min(alpha, 0.5)
                rect.set_alpha(0.05 + alpha)
            if scatter is not None:
                scatter.set_offsets(np.array([self.p_x, self.p_y]).T)
                c = [(r,g,b,min(self.track_certainty[i],1)) for i,(r,g,b) in enumerate(colors)]
                scatter.set_color(c)

            if display_mode == 'quick':
                # this is faster, but doesn't work on all systems
                fig.canvas.draw()
                fig.canvas.flush_events()

            elif display_mode == 'ubuntu_quick':
                # this is even faster, but doesn't work on all systems
                ax.draw_artist(ax.patch)
                ax.draw_artist(img)
                ax.draw_artist(scatter)
                fig.canvas.update()

                fig.canvas.flush_events()
            else:
                # this works on all systems, but is kinda slow
                pylab.pause(1e-8)

            self.image *= decay


    def sensor_loop(self):
        """Handle all data coming from the robot."""
        old_data = None
        buffered_ascii = ''
        while True:
            packet_size = self.retina_packet_size
            # grab the new data
            data = self.connection.receive()

            # combine it with any leftover data from last time through the loop
            if old_data is not None:
                data = old_data + data
                old_data = None

            if packet_size is None:
                # no retina events, so everything should be ascii
                buffered_ascii += data
            else:
                # find the ascii events
                data_all = np.fromstring(data, np.uint8)
                ascii_index = np.where(data_all[::packet_size] < 0x80)[0]

                offset = 0
                while len(ascii_index) > 0:
                    # if there's an ascii event, remove it from the data
                    index = ascii_index[0]*packet_size
                    stop_index = np.where(data_all[index:] >=0x80)[0]
                    if len(stop_index) > 0:
                        stop_index = index + stop_index[0]
                    else:
                        stop_index = len(data)

                    # and add it to the buffered_ascii list
                    buffered_ascii += data[offset+index:offset+stop_index]
                    data_all = np.hstack((data_all[:index],
                                          data_all[stop_index:]))
                    offset += stop_index - index
                    ascii_index = np.where(data_all[::packet_size] < 0x80)[0]

                # handle any partial retina packets
                extra = len(data_all) % packet_size
                if extra != 0:
                    old_data = data[-extra:]
                    data_all = data_all[:-extra]
                if len(data_all) > 0:
                    # now process those retina events
                    self.process_retina(data_all)

            # and process the ascii events too
            while '\n\n' in buffered_ascii:
                cmd, buffered_ascii = buffered_ascii.split('\n\n', 1)
                if '-I' in cmd:
                    dbg, proc_cmd = cmd.split('-I', 1)
                    self.process_ascii('-I'+proc_cmd)


    def process_ascii(self, message):
        try:
            if message[:2] == '-I':
                data = message[2:].split()
                sp_data = data[1:]
                hdr_idx = [ind for ind, s in enumerate(sp_data) if '-S' in s]
                for ind, el in enumerate(hdr_idx):
                    if ind < len(hdr_idx) - 1:
                        vals = sp_data[hdr_idx[ind] + 1:hdr_idx[ind + 1]]
                    else:
                        vals = sp_data[hdr_idx[ind] + 1:]
                    src = int(sp_data[hdr_idx[ind]][2:])
                    for name, value in self.sensor_bitmap.iteritems():
                        if src == value[0]:
                            sliced = value[1]
                            index = self.sensor_map[name]
                            scale = self.sensor_scale[index]
                            # FIXME Check the correct ranges and conversions
                            if scale < 1./6000 or name is not 'bump':
                                sensors = [float.fromhex(x)*scale for x in vals[sliced]]
                            else:
                                sensors = [float(x)*scale for x in vals[sliced]]
                            self.sensor[index] = sensors
                            self.sensor[self.sensor_map[index]] = sensors
        except:
            print('Error processing "%s"' % message)
            import traceback
            traceback.print_exc()

    last_timestamp = None
    def process_retina(self, data):
        packet_size = self.retina_packet_size
        y = data[::packet_size] & 0x7f
        x = data[1::packet_size] & 0x7f
        if self.image is not None:
            value = np.where(data[1::packet_size]>=0x80, 1, -1)
            self.image[y, x] += value

        if self.count_spike_regions is not None:
            tau = 0.05 * 1000000
            for k, region in self.count_spike_regions.items():
                minx, miny, maxx, maxy = region
                index = (minx <= x) & (x<maxx) & (miny <= y) & (y<maxy)
                count = np.sum(index)
                t = (int(data[-2]) << 8) + data[-1]
                if packet_size >= 5:
                    t += int(data[-3]) << 16
                if packet_size >= 6:
                    t += int(data[-4]) << 24

                old_count, old_time = self.count_regions[k]

                dt = float(t - old_time)
                if dt < 0:
                    dt += 1 << ((packet_size - 2) * 8)
                count *= self.count_regions_scale[k]
                count /= dt / 1000.0

                decay = np.exp(-dt/tau)
                new_count = old_count * (decay) + count * (1-decay)

                self.count_regions[k] = new_count, t

        if self.track_periods is not None:
            t = data[2::packet_size].astype(np.uint32)
            t = (t << 8) + data[3::packet_size]
            if packet_size >= 5:
                t = (t << 8) + data[4::packet_size]
            if packet_size >=6:
                t = (t << 8) + data[5::packet_size]

            if self.last_timestamp is not None:
                dt = float(t[-1]) - self.last_timestamp
                if dt < 0:
                    dt += 1 << (8 * (packet_size-2))
            else:
                dt = 1
            self.last_timestamp = t[-1]

            index_off = (data[1::packet_size] & 0x80) == 0

            delta = np.where(index_off, t - self.last_off[x, y], 0)

            self.last_off[x[index_off],
                         y[index_off]] = t[index_off]

            tau = 0.05 * 1000000
            decay = np.exp(-dt/tau)
            self.track_certainty *= decay

            for i, period in enumerate(self.track_periods):
                eta = self.track_eta
                t_exp = period * 2
                sigma_t = self.track_sigma_t    # in microseconds
                sigma_p = self.track_sigma_p    # in pixels
                t_diff = delta.astype(np.float) - t_exp

                w_t = np.exp(-(t_diff**2)/(2*sigma_t**2))
                px = self.p_x[i]
                py = self.p_y[i]

                dist2 = (x - px)**2 + (y - py)**2
                w_p = np.exp(-dist2/(2*sigma_p**2))

                ww = w_t * w_p
                c = sum(ww) * self.track_certainty_scale / dt

                self.track_certainty[i] += (1-decay) * c

                w = eta * ww
                for j in np.where(w > eta * 0.1)[0]:
                        px += w[j] * (x[j] - px)
                        py += w[j] * (y[j] - py)
                self.p_x[i] = px
                self.p_y[i] = py

                '''
                # faster, but less accurate method:
                # update position estimate
                try:
                    r_x = np.average(x, weights=w_t*w_p)
                    r_y = np.average(y, weights=w_t*w_p)
                    self.p_x[i] = (1-eta)*self.p_x[i] + (eta)*r_x
                    self.p_y[i] = (1-eta)*self.p_y[i] + (eta)*r_y
                except ZeroDivisionError:
                    # occurs in np.average if weights sum to zero
                    pass
                '''

            #print self.p_x, self.p_y, self.track_certainty


    def track_spike_rate(self, **regions):
        self.count_spike_regions = regions
        self.count_regions = {}
        self.count_regions_scale = {}
        for k,v in regions.items():
            self.count_regions[k] = [0, 0]
            area = (v[2] - v[0]) * (v[3] - v[1])
            self.count_regions_scale[k] = 200.0 / area

    def get_spike_rate(self, region):
        return self.count_regions[region][0]

    def track_frequencies(self, freqs, sigma_t=100, sigma_p=30, eta=0.3,
                                 certainty_scale=10000):
        freqs = np.array(freqs, dtype=float)
        track_periods = 500000 / freqs
        self.track_certainty_scale = certainty_scale

        self.track_sigma_t = sigma_t
        self.track_sigma_p = sigma_p
        self.track_eta = eta

        self.last_off = np.zeros((128, 128), dtype=np.uint32)
        self.p_x = np.zeros_like(track_periods) + 64.0
        self.p_y = np.zeros_like(track_periods) + 64.0
        self.track_certainty = np.zeros_like(track_periods)
        self.good_events = np.zeros_like(track_periods, dtype=int)
        self.track_periods = track_periods

    def get_frequency_info(self, index):
        x = self.p_x[index] / 64.0 - 1
        y = - self.p_y[index] / 64.0 + 1
        return x, y, self.track_certainty[index]
