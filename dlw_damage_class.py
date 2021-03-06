import math
import numpy as np
import sys
from tqdm import tqdm # For timer bar.
from dlw_log import LogUtil # For logging. Currently DEBUG use only.
#from celery import Celery # For running from web app
#app = Celery('run_model',broker='amqp://', backend='amqp://')

log = LogUtil() # Instanciate the logger utility.

class damage_model(object):
    '''Includes functions to evaluate the damages for the dlw climate model
    '''
    
    '''Functions used in the monte carlo simulation
        
        Functions
        ----------
        Pindyck_temp_map(draws) : function
            Thin tailed gamma distribution
        
        WW_temp_map(draws) : function
            Thicker tailed log-normal distribution
        
        RB_temp_map(draws) : function
            Roe-Baker distribution
        '''

    def __init__(self,my_tree,peak_temp=11.0,disaster_tail=18.0,tip_on=1,temp_map=1,bau_ghg=1000.,pindyck_impact_k=4.5,pindyck_impact_theta=21341.0,pindyck_impact_displace=-.0000746,
                 draws=50,over=10,monte_loops=1,loops=1,dnum=3,force_simul=1,maxh=100.):
                     #draws=500000
        '''Initializes a climate parameter model
                Parameters
        ----------

        my_tree : tree object
            provides the tree structure used to price emissions
            
        peak_temp : float
            determines the probability of a tipping point
        
        disaster_tail : float
            Curvature of the cost function
            
        tip_on : integer
            flag that turns tipping points on (1) or off (0)
            
        temp_map : integer
            the mapping from GHG to temperature
            0 implies pindyck displace gamma
            1 implies Wagner-Weitzman normal
            2 implies Roe-Baker

        bau_ghg : float
            the business-as-usual level of GHG in the atmosphere at time T with no mitigation
        
        pindyck_impact_k : float
            Shape parameter from Pyndyck damage function
        
        pindyck_impact_theta : float
            Scale parameter from Pyndyck damage function
        
        pindyck_impact_displace : float
            Displacement parameter from Pyndyck damage function

        draws : integer
            number of draws per loop

        over : integer
            number of times to go through the draw loop

        monte_loops : integer
            number of full monte carlo simulations to run

        loops : integer
            number of times to go thru the draws * over loop

        dnum : integer
            the number of GHG levels over which damage simulations are created
        
        maxh : float
            time paramter from Pindyck which indicates the time it takes for temp to get half way to its max value for a given level of ghg
        
        '''
        log.log_it("Inside damage_class")
        log.log_it("peak_temp: %i" % peak_temp)
        log.log_it("disaster_tail: %i" % disaster_tail)
        self.my_tree = my_tree
        self.peak_temp = peak_temp
        self.disaster_tail = disaster_tail
        self.tip_on = tip_on
        self.temp_map = temp_map
        self.bau_ghg = bau_ghg
        self.pindyck_impact_k = pindyck_impact_k
        self.pindyck_impact_theta = pindyck_impact_theta
        self.pindyck_impact_displace = pindyck_impact_displace
        self.draws = draws
        self.over = over
        self.monte_loops = monte_loops
        self.loops = loops
        self.dnum = dnum
        self.force_simul = force_simul
        self.maxh = maxh
        
        '''
            these are the Pindyck GHG to temp parameter mappings
        '''
        self.pindyck_temp_k = [ 2.81, 4.6134, 6.14 ]
        self.pindyck_temp_theta = [ 1.6667, 1.5974, 1.53139 ]
        self.pindyck_temp_displace = [ -.25,  -.5,  -1.0 ]
        '''
            these are the Wagner-Weitzman GHG to temp parameter mappings
        '''
        self.ww_temp_ave = [ .573, 1.148, 1.563 ]
        self.ww_temp_stddev = [ .462, .441, .432 ]
        '''
            these are the Roe-Baker GHG to temp parameter mappings
        '''
        self.rb_fbar = [ .75233, .844652, .858332 ]
        self.rb_sigf = [.049921, .033055, .042408 ]
        self.rb_theta = [ 2.304627, 3.333599, 2.356967 ]
        self.damage_function_interpolation_coefficients = np.zeros([self.my_tree.final_states,self.my_tree.nperiods,self.dnum-1,3])
        
        log.log_it("Initializing Damage Function")
        log.log_it("Peak temp parameter = %f Disaster tail parameter = %f" % (self.peak_temp, self.disaster_tail))
        log.log_it(" Tipping points flag = %f" % self.tip_on)
        log.log_it("Temperature map = %f" % self.temp_map)
        log.log_it("BAU GHG reaches = %f" % self.bau_ghg)
        log.log_it(" Pindyck damage parameters(k,theta,displacement) = %f %f %f" % (self.pindyck_impact_k, self.pindyck_impact_theta, self.pindyck_impact_displace))
        log.log_it(" Monte Carlo draws = %i" % (self.draws * self.over))
        
    def damage_function_interpolation(self):
        '''
            use damage function coefficients to create the interpolation parameters
            for use by the damage function        
               
        Returns
        -------
        damage_function_interpolation_coefficients : float
            uses damage function coefficients to create a the damage function
            which returns damages at any time for any given level of GHG
            
        '''
        amat = np.zeros([3,3])
        bmat = np.zeros(3)
        dnum = self.dnum
    
        for state in range(0, self.my_tree.final_states):
            for p in range(0, self.my_tree.nperiods):
                '''   constant = bau damage '''
                self.damage_function_interpolation_coefficients[state][p][dnum-2][2] = self.d[state][p][dnum-1]
                '''   deriv = 0 at bau sets linear term = 0  '''
                self.damage_function_interpolation_coefficients[state][p][dnum-2][1] = 0
                '''   damage at next simul determines curvature  '''
                self.damage_function_interpolation_coefficients[state][p][dnum-2][0] = ( self.d[state][p][dnum-2] - self.damage_function_interpolation_coefficients[state][p][dnum-2][2] ) / self.emit_percentage[dnum-2]**2
                deriv = 2*self.damage_function_interpolation_coefficients[state][p][dnum-2][0]*self.emit_percentage[dnum-2]
            
                for simul in range(1, dnum-1):
                    ''' deriv of damage function at next simul determines first equation  '''
                    amat[0][0] = 2.0 * self.emit_percentage[dnum-simul-1]
                    amat[0][1] = 1.0
                    bmat[0] = deriv
                    '''  damage at next simul determines second equation '''
                    amat[1][0] = self.emit_percentage[dnum-simul-2]**2
                    amat[1][1] = self.emit_percentage[dnum-simul-2]
                    amat[1][2] = 1.0
                    bmat[1] = self.d[state][p][dnum-simul-2]
                    '''  damage at this simul determines third equation  '''
                    amat[2][0] = self.emit_percentage[dnum-simul-1]**2
                    amat[2][1] = self.emit_percentage[dnum-simul-1]
                    amat[2][2] = 1.0
                    bmat[2] = self.d[state][p][dnum-simul-1]
                    '''   solve this system of equations  '''
                    self.damage_function_interpolation_coefficients[state][p][dnum-simul-2] = np.linalg.solve(amat,bmat)
              
        return(self.damage_function_interpolation_coefficients)

    def damage_function(self,x,node):
        '''
            Calculates the damages for any given node, for the path of mitigation actions given by the vector x
        
        Parameters
        ----------

        x : float
            the vector of mitigations

        node : integer
            the node in the my_tree for which the damage is to be calculated
        
        Returns
        -------
        damage : float
            the damages in the state at the given period given mitigation specified
        '''
        if( node >= self.my_tree.x_dim ):
            period = 5
        else :
            period = self.my_tree.period_map[node]

        '''  no damage in period 0 '''
        if (period == 0):
            return(0.)

        '''  find the partition of final states reachable from the given node '''
        if period <= 3:
            first_state = self.my_tree.node_mapping[period-1][node - self.my_tree.decision_period_pointer[period]][0]
            last_state = self.my_tree.node_mapping[period-1][node - self.my_tree.decision_period_pointer[period]][1]
        elif period == 4:
            first_state = node - self.my_tree.decision_period_pointer[period]
            last_state = first_state
        else :
            first_state = node - self.my_tree.x_dim
            last_state = first_state
        pm1 = period-1
        '''
            the damage in the given node is the average over all possible future states (that is the partition reachable from this node)
        '''
        
        average_mitigation = self.average_mitigation( x, node )

        sum_prob = 0.
        damage = 0.
        for state in range(first_state, last_state+1):
            prob = self.my_tree.probs[state]
            sum_prob += prob
            if average_mitigation < self.emit_percentage[1] :
                simul = 1
                damage += prob * (self.damage_function_interpolation_coefficients[state][pm1][simul][0]*average_mitigation**2 + self.damage_function_interpolation_coefficients[state][pm1][simul][1]*average_mitigation + self.damage_function_interpolation_coefficients[state][pm1][simul][2])
            else :
                if average_mitigation < 1.0 :
                    simul = 0
                    damage += prob * (self.damage_function_interpolation_coefficients[state][pm1][simul][0]*average_mitigation**2 + self.damage_function_interpolation_coefficients[state][pm1][simul][1]*average_mitigation + self.damage_function_interpolation_coefficients[state][pm1][simul][2])
                else :
                    simul = 0
                    damage += prob * .5**(10.0*(average_mitigation-1.0)) * (self.damage_function_interpolation_coefficients[state][pm1][simul][0]*average_mitigation**2 + self.damage_function_interpolation_coefficients[state][pm1][simul][1]*average_mitigation + self.damage_function_interpolation_coefficients[state][pm1][simul][2])
                    
        return(damage/sum_prob)

    def d_damage_by_state(self, x, node, j):
        '''
            Calculates the derivative of the damage function for any given node with respect to mitigation at node j
        
        Parameters
        ----------
        x : float
            vector of mitigation values for each node
        
        node : integer
            the node at which the derivative is calculated
        
        j : integer
            the node whose mitigation the derivative of damages is calculated with respect to 
        
        Returns
        -------
        damage_derivative : float
            the derivative of the damage function with respect to changes in mitigation
        '''
        if( node == j ):
            return( 0 )
        if( node >= self.my_tree.x_dim ):
            period = 5
        else :
            period = self.my_tree.period_map[node]

        '''  no damage in period 0 '''
        if (period == 0):
            return(0.)

        '''  find the partition of final states reachable from the given node '''
        if period <= 3:
            first_state = self.my_tree.node_mapping[period-1][node - self.my_tree.decision_period_pointer[period]][0]
            last_state = self.my_tree.node_mapping[period-1][node - self.my_tree.decision_period_pointer[period]][1]
        elif period == 4:
            first_state = node - self.my_tree.decision_period_pointer[period]
            last_state = first_state
        else :
            first_state = node - self.my_tree.x_dim
            last_state = first_state
        pm1 = period-1
        '''
            the damage in the given node is the average over all possible future states (that is the partition reachable from this node)
        '''
        average_mitigation = self.average_mitigation( x, node )
        sum_prob = 0.
        d_damage = 0.
        for state in range(first_state, last_state+1):
            prob = self.my_tree.probs[state]
            sum_prob += prob
            if average_mitigation < self.emit_percentage[1] :
                simul = 1
                d_damage += prob * (2.*self.damage_function_interpolation_coefficients[state][pm1][simul][0]*average_mitigation + self.damage_function_interpolation_coefficients[state][pm1][simul][1])
            else :
                if average_mitigation < 1. :
                    simul = 0
                    d_damage += prob * (2.*self.damage_function_interpolation_coefficients[state][pm1][simul][0]*average_mitigation + self.damage_function_interpolation_coefficients[state][pm1][simul][1])
                else :
                    simul = 0
                    decay = .5**(10.*(average_mitigation-1.))
                    damage = (self.damage_function_interpolation_coefficients[state][pm1][simul][0]*average_mitigation**2 + self.damage_function_interpolation_coefficients[state][pm1][simul][1]*average_mitigation + self.damage_function_interpolation_coefficients[state][pm1][simul][2])
                    ddamage = 2*self.damage_function_interpolation_coefficients[state][pm1][simul][0]*average_mitigation + self.damage_function_interpolation_coefficients[state][pm1][simul][1]
                    ddecay = (-12295127. * 2.**(13.-10.*average_mitigation))/14190495.
                    d_damage += prob * (damage * ddecay + ddamage * decay)

        d_damage = d_damage / sum_prob
        emissions_deriv = self.d_average_mitigation(node, j)

        return(emissions_deriv * d_damage )

    def nd_damage_by_state( self, x, node, j ):
        '''
            Calculates and returns the numerical derivative of damage by state
        
        Parameters
        ----------
        x : float
            Vector of mitigation values for each node
        
        node : integer
            the node for which the damage function derivative is being taken
        
        j : integer
            the node whose mitigation the derivative of damage is being taken with respect to
        
        Returns
        -------
        damage_derivative : float
            numerical gradient of the damage by state function wrt emissions mitigation
        '''
        average_mitigation = self.average_mitigation( x, node)         
        base_damage = self.damage_function(x, node)
        delta_mitigation = .0001
        x[j] += delta_mitigation
        new_damage = self.damage_function(x, node)

        damage_derivative = (new_damage - base_damage) / delta_mitigation

        return damage_derivative
    
    def average_mitigation(self, x, node):
        '''
            Calculates the average mitigation leading up to the damage calculation in "node"
        
        Parameters
        ----------
        x : float
            vector of mitigations in each node
        
        node : integer
            the node for which the average mitigation leading to the damages are being calculated

        Returns
        -------
        average_mitigation : float
            the average mitigation to date for a given node
        '''
        if( node >= self.my_tree.x_dim ):
            period = self.my_tree.nperiods
        else :
            period = self.my_tree.period_map[node]
        if (period == 0):
            return(0.)

        ''' get the emissions at period 0 and initialize emissions and average emissions '''
        emissions_at_p = self.my_tree.bau_of_t(0.)
        period_length = self.my_tree.decision_times[1]
        average_mitigation = x[0] * emissions_at_p * period_length
        total_emissions = emissions_at_p * period_length
        
        '''  find the final state reached by the given node '''
        if period <= self.my_tree.nperiods-2 :
            state = self.my_tree.node_mapping[period-1][node - self.my_tree.decision_period_pointer[period]][0]
        elif period == self.my_tree.nperiods-1 :
            state = node - self.my_tree.decision_period_pointer[period]
        else :
            state = node - self.my_tree.x_dim

        ''' find the node in each period that leads to the node of interest
            for each such node get the emissions mitigation and update the average mitigation and total emissions '''
        for p in range(1, period):
            period_length = self.my_tree.decision_times[p+1] - self.my_tree.decision_times[p]
            emissions_at_p = self.my_tree.bau_of_t(self.my_tree.decision_times[p])
            total_emissions += emissions_at_p * period_length
            average_mitigation += x[ self.my_tree.node_map[p-1][state] ] * emissions_at_p * period_length

        '''   the average mitigation is the emissions weighted average mitigation divided by the total emissions '''
        average_mitigation = average_mitigation / total_emissions
        return(average_mitigation)

    def d_average_mitigation(self, node, j):
        '''Calculates the derivative of average_mitigation at node wrt mitigation at node j
        
        Parameters
        ----------
        node : integer
            the node for which the damages derivative is being calculated

        j : integer
            the derivative of damages is being calculated with respect to mitigation at node j

        Returns
        -------
        deriv_average_mitigation_wrt_xj : float
            the derivative of average_mitigation in the node "node" wrt mitigation at node j
        '''
        j_period = self.my_tree.period_map[j]
        if j_period == 0 :
            period_length = self.my_tree.decision_times[1]
            emissions_at_j = self.my_tree.bau_of_t(0.) * period_length
        else :
            period_length = self.my_tree.decision_times[j_period+1] - self.my_tree.decision_times[j_period]
            emissions_at_j = self.my_tree.bau_of_t(self.my_tree.decision_times[j_period]) * period_length

        ''' prepare to calculate the total emissions '''
        emissions_at_p = self.my_tree.bau_of_t(0.)
        period_length = self.my_tree.decision_times[1]
        total_emissions = emissions_at_p * period_length

        if( node >= self.my_tree.x_dim ):
            period = self.my_tree.nperiods
        else :
            period = self.my_tree.period_map[node]
        
        ''' find the final state reached by the node, and then for each period find the state that reaches that node in the period of the jth node '''
        final_state = 0 
        if( j_period != 0 ):
            if period <= self.my_tree.nperiods-2 :
                final_state = self.my_tree.node_mapping[period-1][node - self.my_tree.decision_period_pointer[period]][0]
            elif period == self.my_tree.nperiods-1 :
                final_state = node - self.my_tree.decision_period_pointer[period]
            else :
                final_state = node - self.my_tree.x_dim
            period_state = self.my_tree.node_map[j_period-1][final_state]
        else:
            period_state = 0

        '''  if node j does not reach the final state reached from node the derivative is zero '''
        if( j != period_state ):
            return( 0. )
        if( j > node ):
            return(0.)

        '''  else calculate the total emissions and the derivative wrt x[j] '''
        for p in range(1, period):
            period_length = self.my_tree.decision_times[p+1] - self.my_tree.decision_times[p]
            emissions_at_p = self.my_tree.bau_of_t(self.my_tree.decision_times[p])
            total_emissions += emissions_at_p * period_length

        deriv_average_mitigation_wrt_xj = emissions_at_j/total_emissions

        return(deriv_average_mitigation_wrt_xj)

    def nd_average_mitigation(self, x, node, j):
        '''Calculates the numerical derivative of average_mitigation wrt mitigation at node j
        
        Parameters
        ----------
        x : float
            vector of mitigations in each node
        
        node : integer
            the node for which the damages derivative is being calculated

        j : integer
            the derivative of damages is being calculated with respect to mitigation at node j

        Returns
        -------
        deriv_average_mitigation_wrt_xj : float
            the derivative of damage in the node "node" wrt mitigation at node j
        '''
        average_mitigation = self.average_mitigation( x, node)
        delta = .0001
        x[j] += delta
        new_average_mitigation = self.average_mitigation( x, node)
        x[j] -= delta
        numerical_deriv = (new_average_mitigation - average_mitigation) / delta

        return(numerical_deriv)

    def initialize_tree(self):
            '''  initialize damage coefficients for recombining tree
                    the state reached by an up-down move is separate from a down-up move because in general the two paths will
                    lead to different degrees of mitigation and therefore of ghg_level
                    a "recombining" tree is one in which the movement from one state to the next through time is nonetheless such that
                    an up move followed by a down move leads to the same fragility, that is damage(ghg_level), as a down move followed by an up move
                    a recombining tree thus models a diffusion process
                    in order to create a recombining tree we first calculate the damage by state separately for each state, but then 
                    the damage in the combined state is set equal to the average damage across both 
            '''
            nperiods = self.my_tree.nperiods
            
            sum_class = np.zeros(nperiods,dtype=int)
            new_state = np.zeros( [nperiods, self.my_tree.final_states], dtype=int )
            temp_prob = np.zeros(self.my_tree.final_states)
            
            for old_state in range(0, self.my_tree.final_states):
                temp_prob[old_state] = self.my_tree.probs[old_state]
                binary_rep = np.zeros(nperiods-1)
                rem = old_state
                digit = nperiods-2
                d_class = 0
                while digit >= 0 :
                    if rem >= 2**digit :
                        rem = rem - 2**digit
                        binary_rep[digit] = 1
                        d_class += 1
                    digit = digit - 1
                sum_class[d_class] += 1
                new_state[d_class, sum_class[d_class]-1 ] = old_state

            old_state = 0
            prob_sum = np.zeros(nperiods)
            for d_class in range(0, nperiods):
                for i in range(0, sum_class[d_class]):
                    prob_sum[d_class] += self.my_tree.probs[ old_state ]
                    old_state += 1
                    
            for period in range(0, nperiods):
                for simul in range(0, self.dnum):
                    d_sum = np.zeros(nperiods)
                    old_state = 0
                    for d_class in range(0, nperiods):
                        for i in range(0, sum_class[d_class]):
                            d_sum[d_class] += self.my_tree.probs[ old_state ] * self.d[ old_state ][ period][simul]
                            old_state += 1
                    for d_class in range(0, nperiods):
                        for i in range(0, sum_class[d_class]):
                            self.d[ new_state[d_class,i]][period][simul] = d_sum[d_class] / prob_sum[d_class]
            old_state = 0
            for d_class in range(0, nperiods):
                for i in range(0, sum_class[d_class]):
                    self.my_tree.probs[new_state[d_class,i]] = temp_prob[old_state]
                    old_state += 1

            for n in range(0, self.my_tree.final_states):
                self.my_tree.node_probs[self.my_tree.decision_period_pointer[nperiods-1]+n] = self.my_tree.probs[n]
            for p in range(1,nperiods-1):
                for n in range(0, self.my_tree.decision_nodes[nperiods-1-p]):
                    sum_probs = 0.0
                    for ns in range( self.my_tree.node_mapping[nperiods-2-p][n][0], self.my_tree.node_mapping[nperiods-2-p][n][1]+1):
                        sum_probs += self.my_tree.probs[ns]
                    self.my_tree.node_probs[self.my_tree.node_map[nperiods-2-p][self.my_tree.node_mapping[nperiods-2-p][n][0]]] = sum_probs
        
    def gammaArray(self, shape, rate, dimension):
        scale = 1/rate
        y = np.random.gamma(shape, scale, dimension)
        return y

    def normalArray(self, mean, stdev, dimension):
        y = np.random.normal(mean, stdev, dimension)
        return y

    def uniformArray(self, dimension):
        y = np.random.random(dimension)
        return y

    def damage_simulation(self):

        '''   Create damage function values in "p-period" version of the Summers - Zeckhauser model

           the damage function simulation is a key input into the pricing engine
           damages are represented in arrays of dimension n x p d(1,1) through d(p,n);
           where n = nstates  p = nperiods 
           these arrays are created by a monte carlo simulation
           each array specifies for each state and time period a damage coefficient
           GHG levels are increasing along a path that leads
           to a given level at a given time in the future, eg a path in which GHG = 1000 ppm in 2200
           a state, 1...nstate is an index of the worst to best damage outcomes
           for each state d(1,i) gives the average percentage damage that occurs
           at the end of period one in that state
           for each state d(2,i) gives the average percentage damage that occurs
           at the end of period two in that state
             ....
           for each state d(p,i) gives the average percentage damage that occurs
           at the end of period p in that state

           these d arrays determine the damage in optimizations that follow

           Up to a point, the monte carlo follows Pindyck(2012) Uncertain Outcomes and Climate Change Policy
             there is a gamma distribution for temperature
             there is a gamma distribution for economic impact(conditional on temp)

           However, in addition, this program adds a probability of a tipping point(conditional on temp)
             this probability is a decreasing function of the parameter peak_temp
             conditional on a tipping point damage itself is a decreasing function of the parameter disaster_tail
             
           priors could be given for key parameters peak_temp and disaster_tail but in this version of the code
               parameters peak_temp and disaster_tail are fixed values

        '''
    
        log.log_it('Global tree structure parameters:')
        log.log_it(' Periods: %i Nodes in tree: %i Final_states: %i' % (self.my_tree.nperiods, self.my_tree.x_dim, self.my_tree.final_states))
        log.log_it(' Horizons: %s' % str(self.my_tree.decision_times))
        log.log_it(' Final state probabilities: %s' % str(self.my_tree.probs))

        log.log_it('Global economic parameters:')
        log.log_it(' Economic growth: %f' % self.my_tree.growth)
        log.log_it(' Elasticity of Intertemporal Substitution: %f  Risk Aversion: %f' % (self.my_tree.eis, self.my_tree.ra))

        log.log_it('Damage parameters:')

        if (self.temp_map == 0):
            log.log_it('  Use the Pindyck displaced gamma distribution mapping GHG into temperature')
        elif (self.temp_map == 1):
            log.log_it('  Use the Wagner-Weitzman log-normal distribution mapping GHG into temperature')
        else:
            log.log_it(' Use the Roe-Baker distribution mapping GHG into temperature')

        if (self.tip_on == 0):
            log.log_it(' tipping points and disaster tail turned OFF')
        else:
            log.log_it(' tipping points and disaster tail turned ON')
            log.log_it(' Peak_temp: %f Disaster_tail %f' % (self.peak_temp, self.disaster_tail))

        log.log_it('Monte Carlo parameters:')
        log.log_it('  Total number of MC simulations: %i' % self.monte_loops)
        log.log_it('  Creating damage coefficients using %i simulations' % (self.draws * self.over * self.monte_loops))
        log.log_it('  Damage coefficients are written to the file: dlw_damage_matrix')

        f = open('\\Users\\Bob Litterman\\Dropbox\\EZ Climate calibration paper\\dlw code\\dlw_damage_matrix', 'w')
        f.write(str('\n'))
        f.write( '%15i' % self.my_tree.nperiods + ' ' + '%15i' % self.my_tree.x_dim + ' ' + '%15i' % self.my_tree.final_states)
        f.write(str('\n'))
        f.write( '%15i' % self.monte_loops + ' ' + '%15i' % self.draws + ' ' + '%15i' % self.over + ' ' + '%15i' % self.tip_on)
        f.write(str('\n'))
        f.write( '%15f' % self.disaster_tail + ' ' + '%15f' % self.peak_temp + ' ' + '%15f' % self.temp_map + ' ' + '%15f' % self.my_tree.growth)
        f.write(str('\n'))
        for i in range(0, self.my_tree.final_states):
            f.write( '%12f' % self.my_tree.probs[i])
        f.write(str('\n'))
        for i in range(0, self.my_tree.nperiods+1):
            f.write( '%12f' % self.my_tree.decision_times[i])
            
        f.write(str('\n'))

        '''  loop over Monte Carlo monte_loops times, if it is desired to generate multiple sets of
          damage coefficient results on one file 
        '''
        for outerloop in range(0, self.monte_loops):

            '''  there are self.dnum simulations for different paths of GHG, eg leading to 450, 650, and 1000 ppm
             the damage coefficients along these paths are interpolated in the optimization
             in order to determine the damage along any given mitigation policy
             begin by allocating space for simulation results
            '''
            for rb in range(0, self.dnum):
                consump = np.zeros([self.draws,self.my_tree.nperiods])
                tmp = np.zeros([self.draws,self.my_tree.nperiods])
                damage = np.zeros([self.draws,self.my_tree.nperiods])
                temp_at_h = np.zeros([self.my_tree.nperiods])

                '''   create exogenous path for consumption before damages
                '''
                peak_con = []

                for p in range(self.my_tree.nperiods):
                    peak_con.append( math.exp( self.my_tree.growth * self.my_tree.decision_times[p+1] ) )

                    '''   to minimize overall memory allocation, the total number of simulations:  self.loops * self.over * self.draws
                        is created in random simulations with self.draws each time through the inner loop
                    '''

                for lp in range(0,self.loops):
                    log.log_it('loop: %i  simul with GHG level = %f' % (lp, self.ww_ghg[rb]))
                    d = np.zeros([self.my_tree.final_states,self.my_tree.nperiods])

                    ''' loop over the Monte Carlo over times, in order to increase accuracy
                    '''
                    for redraw in tqdm(range(0,self.over)):
        
                        '''  draw random outcomes for temperature and economic impact per Pindyck paper
                        '''    
                        #print(' percent done so far ', (100. * redraw) / float(self.over))
                        if (self.temp_map == 0):
                            temperature = self.gammaArray(self.pindyck_temp_k[rb], self.pindyck_temp_theta[rb],self.draws)+self.pindyck_temp_displace[rb]
                        elif (self.temp_map == 1):
                            temperature = self.normalArray(self.ww_temp_ave[rb], self.ww_temp_stddev[rb],self.draws)
                        else :
                            temperature = self.normalArray(self.rb_fbar[rb], self.rb_sigf[rb], self.draws)

                        '''   start with the Pindyck gamma distribution mapping temperature into damages
                        '''
                        impact = (self.gammaArray(self.pindyck_impact_k, self.pindyck_impact_theta, self.draws)+self.pindyck_impact_displace )
    
                        ''' disaster is a random variable allowing for a tipping point to occur                      
                           with a given probability, leading to a disaster and a "disaster_tail" impact on consumption
                        '''
                        disaster = self.uniformArray([self.draws,self.my_tree.nperiods])
                        ''' disaster consumption gives consumption conditional on disaster, based on the parameter pd.disaster_tail
                        '''
                        disaster_consumption = self.gammaArray(1.0,self.disaster_tail,self.draws)

                        for counter in np.arange(0,self.draws):
                            if (self.temp_map == 1):        
                                temperature[counter] = math.exp(temperature[counter])
                            if (self.temp_map == 2):
                                temperature[counter] = 1.0 / (1.0 - temperature[counter]) - self.rb_theta[rb]
    
                            '''    first_bp is a flag indicating whether a tipping point has already occurred (true if first_bp == 1)
                            '''
                            first_bp = 0
    
                            for p in np.arange(0,self.my_tree.nperiods):
                                ''' implementation of the temperature and economic impacts from Pindyck[2012] page 6
                                '''
                                temperature[counter] = max( 0.0, temperature[counter] )
                                temp_at_h[p] = 2. * temperature[counter] * ( 1. - .5**(self.my_tree.decision_times[p+1]/self.maxh) )
                                tmp[counter,p] = temp_at_h[p]
    
                                ''' Now calculate the economic impact  Pindyck[2009]
                                '''
                                end_time = self.my_tree.decision_times[p+1]
                                ''' Pindyck equation 4
                                '''
                                term1 = -2.0 * impact[counter] * self.maxh * temperature[counter] / -0.693147181
                                term2 = (self.my_tree.growth - 2.0 * impact[counter] * temperature[counter]) * end_time
                                term3 = ( 2.0 * impact[counter] * self.maxh * temperature[counter] * .5**(end_time/self.maxh) ) / -0.693147181
                                growthcon = math.exp( term1 + term2 + term3)
                                consump[counter,p] = growthcon
      
                                '''  now add the tipping points
                                '''
                            period_length = self.my_tree.decision_times[1]
                            for p in np.arange(0,self.my_tree.nperiods):
                                ave_prob_of_survival = 1. - (temp_at_h[p] / max( temp_at_h[p], self.peak_temp ) )**2
                                if p>0 :
                                    period_length= self.my_tree.decision_times[p+1]-self.my_tree.decision_times[p]
                                else :
                                    period_length = self.my_tree.decision_times[1]
                                prob_of_survival_this_period = ave_prob_of_survival**( period_length / self.my_tree.peak_temp_interval )
                                disaster_bar = prob_of_survival_this_period
                                '''    set disaster_bar = 1.0 to turn off tipping points
                                '''
                                if (self.tip_on == 0) :
                                    disaster_bar = 1.0
                                '''   determine whether a tipping point has occurred,  if so hit consumption for all periods after this date
                                '''
                                if( disaster[counter,p] > disaster_bar and first_bp == 0 ):
                                    for pp in range(p,self.my_tree.nperiods):
                                        consump[counter,pp] = consump[counter,pp] * math.exp(-disaster_consumption[counter])
                                        first_bp = 1
                            '''   sort on last column
                            '''
                        consump = consump[ consump[:,self.my_tree.nperiods-1].argsort()]
                        tmp = tmp[ tmp[:,self.my_tree.nperiods-1].argsort()]

                        for counter in np.arange(0,self.draws):
                            for p in np.arange(0,self.my_tree.nperiods):
                                damage[counter,p] = 1. - consump[counter,p]/peak_con[p]

                        firstob = 0
                        lastob = int(self.my_tree.probs[0]*(self.draws-1))
                        for n in np.arange(0,self.my_tree.final_states):
      
                            ''' associate the average damage in the range firstob->lastob with state n
                            '''
      
                            for p in np.arange(0,self.my_tree.nperiods):
                                d[n,p] = d[n,p] + damage[range(firstob,lastob),p].mean()
                            firstob = lastob + 1
                            if( n < self.my_tree.final_states-1 ):
                                lastob = int(sum(self.my_tree.probs[0:n+2]) * (self.draws-1)-1)
                    d = d / self.over

                    ''' put the d matrix on a file
                    '''

                    f.write(str('\n'))
                    for n in range(0,self.my_tree.final_states):
                        for p in range(0,self.my_tree.nperiods):
                            f.write( '%15f' % d[n,p] + ' ' )
                        f.write(str('\n'))
                    f.write(str('\n'))
        f.close()

    def damage_function_initialization(self):
        '''Reads the monte carlo simulation from a file,
            if neccessary, runs a new monte carlo simulation
            and puts the results on a file

            bau_emissions is the business-as-usual amount of emissions
            that is the emissions from time 0 to time T with no mitigation
        '''
        
        self.bau_emissions = self.bau_ghg - 400.
        log.log_it('business-as-usual increase in CO2 ppm: %f' % self.bau_emissions)
        ''' For now we hardwire 3 simulations at ghg levels of 450, 650, and 1000 to calculate damages
        '''
        
        self.ww_ghg = [ 450, 650, 1000 ]
        
        self.emit_percentage = np.zeros( self.dnum )
        self.d = np.zeros( [self.my_tree.final_states,self.my_tree.nperiods,self.dnum] )
 
        for simul in range(0, self.dnum):
          self.emit_percentage[simul] = 1 - float(self.ww_ghg[simul]-400.0)/self.bau_emissions
        log.log_it('simulations emissions percentages: %s' % str(self.emit_percentage))

        if( self.force_simul == 1 ):
            self.damage_simulation()
            self.force_simul = 0 
        else:
            log.log_it("Checking match between monte carlo file parameters and current run parameters")

        f = open('\\Users\\Bob Litterman\\Dropbox\\EZ Climate calibration paper\\dlw code\\dlw_damage_matrix', 'r')
        line = f.readline()
        nperiods, x_dim, final_states = [int(x) for x in f.readline().split()]
        if (nperiods == self.my_tree.nperiods) :
            log.log_it("monte file nperiods = %i" % nperiods)
        else:
            self.force_simul = 1
        if (x_dim == self.my_tree.x_dim) :
            log.log_it("monte file x_dim = %i" % x_dim)
        else:
            self.force_simul = 1
        if (final_states == self.my_tree.final_states) :
            log.log_it("monte file final_states = %i" % final_states)
        else:
            self.force_simul = 1
        monte_loops, draws, over, tip_on = [int(x) for x in f.readline().split()]
        if (monte_loops == self.monte_loops) :
            log.log_it("monte file monte_loops = %i" % monte_loops)
        else:
            self.force_simul = 1
        if (draws == self.draws) :
            log.log_it("monte file draws = %i" % draws)
        else:
            self.force_simul = 1
        if (over == self.over) :
            log.log_it("monte file over = %i" % over)
        else:
            self.force_simul = 1
        if (tip_on == self.tip_on) :
            log.log_it("monte file tip_on = %i" % tip_on)
        else:
            self.force_simul = 1
        disaster_tail, peak_temp, temp_map, growth = [float(x) for x in f.readline().split()]
        if (disaster_tail == self.disaster_tail) :
            log.log_it("monte file disaster_tail = %f" % disaster_tail)
        else:
            self.force_simul = 1
        if (peak_temp == self.peak_temp) :
            log.log_it("monte file peak_temp = %f" % peak_temp)
        else:
            self.force_simul = 1
        if (temp_map == self.temp_map) :
            log.log_it("monte file temp_map = %f" % temp_map)
        else:
            self.force_simul = 1
        if (growth == self.my_tree.growth) :
            log.log_it("monte file growth = %f" % growth)
        else:
            self.force_simul = 1
        log.log_it('check: %if' % self.force_simul)
        probs = [float(x) for x in f.readline().split()]
        for i in range(0, final_states):
            if abs(probs[i]-self.my_tree.probs[i]) > .0001 :
                self.force_simul = 1
        horizons = [float(x) for x in f.readline().split()]
        for i in range(0, nperiods):
            if horizons[i] != self.my_tree.decision_times[i] :
                self.force_simul = 1
        if self.force_simul == 1 :
            log.log_it("PROGRAM HALT: parmameter on Monte Carlo file does not match current run -- set force_simul = 1 to create new monte carlo file")
            sys.exit(0)

        if self.my_tree.nperiods <= 5 :
            for simul in range(0, self.dnum):
              line = f.readline()
              for n in range(0,self.my_tree.final_states):
                  self.d[n][0][simul], self.d[n][1][simul], self.d[n][2][simul], self.d[n][3][simul], self.d[n][4][simul] = [float(x) for x in f.readline().split()]
              '''  if needed for more periods use something like this
                 d[n][0][simul], d[n][1][simul], d[n][2][simul], d[n][3][simul], d[n][4][simul], d[n][5][simul] = [float(x) for x in f.readline().split()]
              '''   
              line = f.readline()
            f.close()
        else :
            for simul in range(0, self.dnum):
              line = f.readline()
              for n in range(0,self.my_tree.final_states):
                  self.d[n][0][simul], self.d[n][1][simul], self.d[n][2][simul], self.d[n][3][simul], self.d[n][4][simul], self.d[n][5][simul] = [float(x) for x in f.readline().split()]
                  '''  if needed for more periods use something like this
                     d[n][0][simul], d[n][1][simul], d[n][2][simul], d[n][3][simul], d[n][4][simul], d[n][5][simul] = [float(x) for x in f.readline().split()]
                  '''   
              line = f.readline()
            f.close()      

        return(self.d)

    
