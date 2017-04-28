Data Transfer Simulator
=====================================

The __Data Transfer Simulator__ is a heap-based discrete event simulator. 
It was built as part of the __Socket Intents__ project to evaluate the benefits of seamlessly using multiple interfaces and scheduling requests according tor our polices.

Copyright
-----
Copyright (c) 2015-2017, Internet Network Architectures Group, Berlin Institute of Technology,
Mirko Palmer and Philipp S. Tiesel.  
All rights reserved.
This project has been licensed under the THE RELAXED CRAPL v0 BETA 1

Simulator Design
-----

The simulator takes a Web page including all Web objects and their dependencies
(represented as a .har file), the Socket Intents Policy, and a list of network interfaces
with their path characteristics as input. The simulator replays the Web page download by
transferring all Web page objects while respecting their inter-dependencies. It uses the
policy to distribute the object transfers across the interfaces and calculates the total
page load time.

Since our simulator knows all object inter-dependencies a priori, it can decide when a
transfer can be scheduled, i.e, whether all objects that it depends upon have already
been loaded. To schedule a transfer we assign it to a connection. This is the job of the
policy module which returns either an existing TCP/MPTCP connection, an interface, or a
list of interfaces to use for the new connection, or postpones the transfer if the limit
of parallel connections has been reached. A connection is reused if the host name matches
and it is either idle or it is expected to become idle before a new connection can be
established.

The simulator then determines the next event for this connection. This can be the
completion of a transfer or a TCP event. TCP events are triggered by connection handling,
TLS handshake, changed available bandwidth share, and once per RTT during slow-start. To
simulate slow-start and fair band- width sharing, we keep track of the current throughput
for each connection. This is updated according to TCP slow-start and capped by the
congestion window or the available bandwidth share of that interface to assure TCP
fairness7. Our underlying assumption is that TCP tries to fairly share the available
bandwidth between all parallel connections. Rather than fully simulating the
congestion avoidance of TCP we assume instantaneous convergence to the appropriate
bandwidth share. The available bandwidth share of each interface is potentially adjusted
by each connection event for that interface. If needed the time of the next event is then
adjusted accordingly. When a transfer finishes, the simulator records the time, marks all
transfers that depend on it as enabled, and schedules them. If it is the last transfer
the total page load time is reported.

Since Socket Intents Policies can use transfer predictions, policies can reuse the
simulator logic to obtain an estimate of the completion time given the current state and
an inter- face/connection option. This is realized by partially cloning the simulator’s
state, including all currently active transfers, and simulating the completion time for
that transfer.

The simulator supports persistent connections with and without pipelining for TCP as well
as MPTCP connections across multiple interfaces. It uses a default connection timeout of
30 seconds and limits the number of parallel connections per server to six and the
overall number of connections to 17. This corresponds to the defaults of the browser we
use to retrieve our workload. We simulate TCP slow-start using a configurable initial
congestion window size with a default value of 10 segments


Simulator Implementation
-----

The Web Transfer Simulator as a heap- based discrete event simulator. It models the
process of loading a web page by keeping track of the transfers’, connections’ and
interfaces’ status.

Each transfer corresponds to a Web object which contains the object size, its
relationship to other transfers, if the object was transferred via HTTPS, and the server
hostname. The connections are responsible for estimating and updating the completion
times of the transfers which are assigned to them and for simulating (MP)TCP. In case of
MPTCP, we maintain a master connection and per interface subflows. The interfaces bundle
the connections and are used to calculate the available bandwidth shares.

The transfer-manager keeps track of all transfers and informs the policy if a transfer
can be scheduled. The policy is the main decision-making entity of the simulation. The
policy determines which interface(s) to use or which connection to re-use for each
transfer by choosing the most appropriate one. The policy then notifies the
transfer-manager to schedule the transfer.


Usage
-----

 mkdir workload
 # place workloads (.har files) there - one directory per dataset
 git clone git@github.com:fg-inet/dtsimulator.git
 ln -s dtsimulator/scripts/* .
 # edit ./mkjobs.sh and generateTasks.py do suite your needs
 ./mkjobs.sh
 