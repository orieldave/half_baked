#!/usr/bin/env python3

"""Test script for ferment and bake classes."""

import re
import math
from datetime import datetime, timedelta


class Ferment:
    """Fermentation step for a specified time and temp.

    Time and temperature are fixed by the following formula:
        new_temp = old_temp - c * log(new_time / old_time)
    where:
        c = double_temp / log(2)
    and double_temp is therefore the increase/decrease in temperature
    required to halve/double the ferment time. Heuristically for bread,
    this is set at 8 C (17 F).
    """

    # Defaults
    default_double_temp = 8.0
    default_temp = 20.0

    def __init__(
            self, name, hours=None, start_time=None, end_time=None,
            temp=default_temp, double_temp=default_double_temp):
        """
        Init with time (in hours or start/end) and temp (C).

        If hours is None, it is calculated from start/end times.
        """

        self.name = name
        if hours:
            self.hours = float(hours)
        else:
            self.hours = float((end_time - start_time).seconds/3600)
        self.temp = float(temp)
        self.double_temp = float(double_temp)
        self.start_time = start_time


    def get_args(self):
        """Return dict of init args."""

        init_args = {
            'name': self.name,
            'hours': self.hours,
            'start_time': self.start_time,
            'temp': self.temp,
            'double_temp': self.double_temp
            }

        return init_args


    def get_end_time(self):
        """Return self.start_time offset by self.hours"""

        if self.start_time:
            return self.start_time + timedelta(hours=self.hours)
        else:
            return None


    def change_hours(self, new_hours):
        """Change ferment time in hours, adjust temp accordingly.

        Temperature is set by:
            new_temp = old_temp - c * log(new_time / old_time)
        where
            c = double_temp / log(2)
        """

        c = self.double_temp / math.log(2)
        new_temp = self.temp - (c * math.log(float(new_hours) / self.hours))
        self.temp = new_temp
        self.hours = float(new_hours)


    def change_temp(self, new_temp):
        """Change ferment temp in C, adjust time (in hours) accordingly.

        Time is set by:
            new_time = old_time * exp((old_temp - new_temp) / c)
        where
            c = double_temp / log(2)
        """

        # new_time = old_time * exp( (inv_c) * (old_temp - new_temp))
        inv_c = math.log(2) / self.double_temp
        new_hours = self.hours * math.exp(inv_c * (self.temp - float(new_temp)))
        self.hours = new_hours
        self.temp = float(new_temp)


    def change_times(self, new_start_time=None, new_end_time=None):
        """Set start/end time. If both are given, change hours too."""

        if new_start_time:
            if new_end_time:
                self.change_hours((new_end_time - new_start_time).seconds/3600)

            self.start_time = new_start_time

        elif new_end_time:
            self.start_time = new_end_time - timedelta(hours = self.hours)

        else:
            self.start_time = None


    def print_name(self):
        """Print self.name."""

        print('Ferment "{}"'.format(self.name))


    def print_values(self, short=True):
        """Print all values."""

        self.print_name()
        print('Time: \t{:.2f} hours'.format(self.hours))
        print('Temp: \t{:.2f} C'.format(self.temp))
        print('Start: \t{:%a %H.%M}'.format(self.start_time))
        print('End: \t{:%a %H.%M}'.format(self.get_end_time()))

        if not short:
            print(
                'Temp change to double/halve time: {:.2f} C'\
                .format(self.double_temp)
                )



class Bake:
    """Bake sequence consisting of multiple fermentation steps.

    Each stage is a separate Ferment object with start times synced
    to ensure no gaps between stages.

    Default stages (at 20C):
        1. Refresh (24 hours)
        2. Feed (8 hours)
        3. Bulk (12 hours)
        4. Proof (2 hours)
    """

    # Defaults
    default_args = {
        'temp': 20.0,
        }

    default_ferment_list = [
        {'name': 'refresh', 'hours': 24},
        {'name': 'feed', 'hours': 8},
        {'name': 'bulk', 'hours': 12},
        {'name': 'proof', 'hours': 2}
        ]


    def __init__(self, ferment_list=default_ferment_list, name=None):
        """Create bake object from list of ferment args for each stage.

        Args:
            * ferment_args: list of dicts of ferment object args
            * name: string name for object
        """

        self.name = name
        self.ferments = []
        self.update_ferment_index()

        for ferment_args in ferment_list:
            self.add_ferment(**ferment_args)


    def add_ferment(self, index=None, **ferment_args):
        """
        Create ferment object from ferment args, append to self.ferments list.

        Args:
        * ferment_args -- keyword args for creating ferment object
        * index -- int, index to insert to instead of append

        Any args in default_args are applied if not specified in ferment_args.
        If index is not None, insert is used, otherwise append.
        """

        # Add args from defaults if not in ferment_args
        for k, v in self.default_args.items():
            if k not in ferment_args.keys():
                ferment_args[k] = v

        # Make ferment from ferment_args
        ferment = Ferment(**ferment_args)

        # Check ferment.name is unique and append '_' if not
        while ferment.name in self.ferment_index.keys():
            ferment.name = '{}_'.format(ferment.name)

        if index is None:
            index = len(self.ferments)

        self.ferments.insert(index, ferment)
        self.update_ferment_index()
        self.sync_times(index)


    def remove_ferment(self, index):
        """Remove ferment from bake, specified by index."""

        del self.ferments[index]
        self.update_ferment_index()
        self.sync_times()


    def update_ferment_index(self):
        """
        Update dict of name:index to be consistent with list of
        ferments.
        """

        self.ferment_index = {
            f.name: index for (index, f) in enumerate(self.ferments)
            }


    def sync_times(self, index=0):
        """
        Adjust start_time of each ferment, using index ferment as
        reference.

        From reference ferment, change other start times to ensure no
        gaps between ferments.
        Never changes length of ferments (ferment.hours).

        If index ferment.start_time is not None, uses this as reference.
        Else if some other not None start_time, uses this.
        Else do nothing (all start_times are None).
        """

        n_ferments = len(self.ferments)

        # Search for not None start_time in ferments, starting with index
        ref_index = None
        for i in [index] + list(range(n_ferments)):
            if self.ferments[i].start_time is not None:
                ref_index = i
                break

        if ref_index is not None:
            for i in range(ref_index+1, n_ferments):
                # Set next_start_time = prev_end_time
                start_time_i = self.ferments[i-1].get_end_time()
                self.ferments[i].change_times(start_time_i)

            for i in range(ref_index-1, -1, -1):
                # Set prev_start_time = start_time - prev_hours
                start_time_i = self.ferments[i+1].start_time \
                    - timedelta(hours = self.ferments[i].hours)
                self.ferments[i].change_times(start_time_i)


    def change_time(
            self, index, hours=None, start_time=None, end_time=None):
        """Change start_time and/or hours of index ferment."""

        if hours:
            # Just change number of hours
            self.ferments[index].change_hours(hours)
        else:
            # Change start_time (and hours if end_time is specified)
            self.ferments[index].change_times(start_time, end_time)

        self.sync_times(index)


    def change_temp(self, index, temp):
        """Change temp of index ferment."""

        self.ferments[index].change_temp(temp)
        self.sync_times(index)


    def print_bake(self, verbose=True):
        """Print name of each ferment, also values if verbose == True."""

        print('\nBake "{}"'.format(self.name))
        for ferment in self.ferments:
            print('Index: \t{}'.format(self.ferment_index[ferment.name]))
            if verbose:
                ferment.print_values()
                print('')
            else:
                ferment.print_name()





### TESTING ###

# Use case: initialise with default bake
# Allow to make changes until done, print each time

'''
bake_name = 'test'

bake = Bake(name=bake_name)

input_help = """
    h -- help \
    a <name> <index> -- add ferment \
    r <name> -- remove ferment \
    ...
    """
bake_is_done = False
while not bake_is_done:

    bake.print_bake()

    action = raw_input('Enter: keyword [args]')
'''




tmp = Ferment(name='test', hours=8, temp=22)
tmp.change_hours(16)
tmp.change_hours(6)
tmp.change_temp(30)

tmp.change_times(datetime.today())
tmp.change_times(datetime.today(), datetime.today() + timedelta(hours=8))
tmp.change_times(datetime.today(), datetime.today() + timedelta(hours=4))

bake = Bake()
bake.add_ferment(**tmp.get_args())
bake.add_ferment(index=-1, **tmp.get_args())


bake.change_time(1, start_time=datetime.today())

bake.add_ferment(index=2, **tmp.get_args())

bake.remove_ferment(3)

bake.remove_ferment(0)

bake.change_temp(1, 10)
bake.change_temp(1, 40)
bake.print_bake()



#bake2 = Bake()



'''
td_feed_starter = timedelta(hours=8)
td_bulk = timedelta(hours
td_shape = 'sat 22.30'
td_bake = 'sun 10.30'

# Inputs
ts_feed_starter = 'sat 09.30'
ts_refresh_starter = 'fri 09.30'
ts_mix = 'sat 14.30'
ts_shape = 'sat 22.30'
ts_bake = 'sun 10.30'

td_refresh_starter = timedelta(hours=24)

def coerce_datetime_to_format(s):
    """Split into str and num, str parsed as %a, num as %H%M, return string"""

    # TODO

    return s



t_format = '%a %H.%M'

t_feed_starter = strptime(ts_feed_starter, t_format)
t_refresh_starter = t_feed_starter - td_refresh_starter


ts_feed_starter = '09.30'
'''
