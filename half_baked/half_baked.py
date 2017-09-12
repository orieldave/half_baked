#!/usr/bin/env python3

"""
    Flask app to compute ferment times/temps for baking.
"""

import re
import os
import math
from datetime import datetime, timedelta
#from datetime.datetime import strptime

from flask import Flask, request, session, g, redirect, url_for, abort, \
     render_template, flash


### FLASK
app = Flask(__name__) # create the application instance
app.config.from_object(__name__) # load config from this file

# Load default config and override config from an environment variable

#DATABASE=os.path.join(app.root_path, 'flaskr.db'),
#USERNAME='admin',
#PASSWORD='default'
app.config.update(dict(
    SECRET_KEY='test'
))

app.config.from_envvar('HALFBAKED_SETTINGS', silent=True)


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
        self.temp = float(temp)
        self.double_temp = float(double_temp)

        # Hours is either explicit or end_time - start_time
        if hours:
            self.hours = float(hours)
        else:
            self.hours = float((end_time - start_time).seconds/3600)

        # Start is either expicit or end_time - hours
        self.start_time = start_time
        if (start_time is None) and (end_time is not None):
            self.start_time = end_time - timedelta(hours=hours)


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


    # Printing

    def get_name_str(self):
        """Return string of self.name."""
        return '{}'.format(self.name)

    def get_time_str(self):
        """Return string of self.time."""
        return '{:.2f}'.format(self.hours)

    def get_temp_str(self):
        """Return string of self.temp."""
        return '{:.2f}'.format(self.temp)

    def get_start_str(self):
        """Return string of self.start_time."""
        if self.start_time is not None:
            return '{:%a %H.%M}'.format(self.start_time)
        else:
            return 'None'

    def get_end_str(self):
        """Return string of self.get_end_time."""

        if self.start_time is not None:
            return '{:%a %H.%M}'.format(self.get_end_time())
        else:
            return 'None'

    def get_double_time_str(self):
        """Return string of self.double_time."""

        return '{:.2f}'.format(self.double_temp)


    def print_name(self):
        """Print name."""

        print(self.get_name_str())


    def print_values(self, verbose=False):
        """Print all values."""

        self.print_name()
        print(self.get_time_str())
        print(self.get_temp_str())

        if self.start_time is not None:
            print(self.get_start_str())
            print(self.get_end_str())

        if verbose:
            print(self.get_double_time_str())



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


    def get_args(self):
        """Return dict of init args."""

        init_args = {
            'name': self.name,
            'ferment_list': [
                ferment.get_args() for ferment in self.ferments
                ]
            }

        return init_args


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

        if n_ferments > 0:
            # Search for not None start_time in ferments,
            # starting with index
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



    def change_times(self, index, start_time=None, end_time=None):
        """Change start_time of index ferment."""
        # Change start_time (and hours if end_time is specified)
        self.ferments[index].change_times(start_time, end_time)
        self.sync_times(index)

    def change_hours(self, index, hours):
        """Change hours of index ferment."""

        self.ferments[index].change_hours(hours)
        self.sync_times(index)


    def change_temp(self, index, temp):
        """Change temp of index ferment."""

        self.ferments[index].change_temp(temp)
        self.sync_times(index)




    # Printing

    def get_name_str(self):
        """Return string of self.name."""
        return '{}'.format(self.name)


    def get_ferment_name_str(self, ferment):
        """Return string of self.name."""

        index = self.ferment_index[ferment.name]
        return '{}. Ferment "{}"'.format(index+1, ferment.get_name_str())


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


    def get_n_ferments(self):
        """"""
        return len(self.ferments)



def html_strptime(s):
    """"""
    html_format = '%Y-%m-%dT%H:%M'
    return datetime.strptime(s, html_format)


# Store bake_args in flask session object
# Recreate bake from these whenever needed


@app.route('/', methods=['GET', 'POST'])
def home():
    """Home page."""

    if request.method == 'POST':
        bake_name = request.form['bake_name']
        if request.form['create'] == 'Default':
            session['bake_args'] = {'name': bake_name}
        else:
            session['bake_args'] = {
                'ferment_list': [], 'name': bake_name
                }
        return redirect(url_for('show_bake'))
    return render_template('home.html')


@app.route('/show_bake', methods=['GET', 'POST'])
def show_bake():
    """Show bake."""

    if not session.get('bake_args'):
        return redirect(url_for('home'))
    else:
        bake = Bake(**session['bake_args'])
        return render_template('show_bake.html', bake=bake)


@app.route('/add_ferment/<int:ferment_index>', methods=['GET', 'POST'])
def add_ferment(ferment_index):
    """Add ferment at position <ferment_index>."""

    # Create bake object from bake_args
    bake = Bake(**session['bake_args'])

    if request.method == 'POST':
        if request.form['add_or_cancel'] == 'Cancel':
            # Return to show_bake
            return redirect(url_for('show_bake'))
        else:
            # Process inputs
            inputs = [
                'ferment_name', 'ferment_temp', 'ferment_time',
                'ferment_start', 'ferment_end'
                ]
            cast_funcs = [str, float, float, html_strptime, html_strptime]
            values = {k:None for k in inputs}
            casts = {k:f for k,f in zip(inputs, cast_funcs)}

            for k in inputs:
                val = request.form[k]
                if len(val) > 0:
                    values[k] = casts[k](val)

            bake.add_ferment(
                ferment_index,
                name=values['ferment_name'],
                temp=values['ferment_temp'],
                hours=values['ferment_time'],
                start_time=values['ferment_start'],
                end_time=values['ferment_end']
                )

            session['bake_args'] = bake.get_args()
            return redirect(url_for('show_bake'))

    return render_template(
        'add_ferment.html', ferment_index=ferment_index
        )

@app.route('/edit_ferment/<ferment_name>', methods=['GET', 'POST'])
def edit_ferment(ferment_name):
    """Edit ferment <ferment_name>."""

    # Create bake object from bake_args
    bake = Bake(**session['bake_args'])
    ferment_index = bake.ferment_index[ferment_name]
    ferment = bake.ferments[ferment_index]

    if request.method == 'POST':
        if request.form['add_or_cancel'] == 'Cancel':
            # Return to show_bake
            return redirect(url_for('show_bake'))
        else:
            # Process inputs
            inputs = [
                'ferment_temp', 'ferment_time',
                'ferment_start', 'ferment_end'
                ]
            cast_funcs = [float, float, html_strptime, html_strptime]
            values = {k:None for k in inputs}
            casts = {k:f for k,f in zip(inputs, cast_funcs)}

            for k in inputs:
                val = request.form[k]
                if len(val) > 0:
                    values[k] = casts[k](val)

            if values['ferment_temp'] is not None:
                # Change temp
                bake.change_temp(ferment_index, values['ferment_temp'])

            if values['ferment_time'] is not None:
                # Change hours
                bake.change_hours(ferment_index, values['ferment_time'])

            if (values['ferment_start'] is not None) \
                or (values['ferment_end'] is not None):
                # Then change times
                bake.change_times(
                    ferment_index, values['ferment_start'],
                    values['ferment_end']
                    )

            session['bake_args'] = bake.get_args()
            return redirect(url_for('show_bake'))

    return render_template(
        'edit_ferment.html', ferment=ferment
        )


@app.route('/delete_ferment/<ferment_name>', methods=['GET', 'POST'])
def delete_ferment(ferment_name):
    """Delete ferment."""

    bake = Bake(**session['bake_args'])
    bake.remove_ferment(bake.ferment_index[ferment_name])
    session['bake_args'] = bake.get_args()

    return redirect(url_for('show_bake'))



### TODO ###
# Fix add_ferment issue that default args won't be used if arg given as None

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
