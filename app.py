from flask import Flask, Request
from flask_restful import reqparse, abort, Api, Resource
import numpy as np


# Werkzeug >= 2.1 raises 415 when request.json is read on a non-JSON request,
# which breaks reqparse's default ('json', 'values') lookup for form data.
# Return None instead so reqparse falls through to form/query values.
class LenientJSONRequest(Request):
    def on_json_loading_failed(self, e):
        if e is None:
            return None
        return super().on_json_loading_failed(e)

app = Flask(__name__)
app.request_class = LenientJSONRequest
api = Api(app)

compute_forcing_terms = {
    'forcing_term1': {'forcing_term': '0.9'},
    'forcing_term2': {'forcing_term': '0.1'},
    'forcing_term3': {'forcing_term': '0.5'},
}

# Input layer x1..x6 (see network.jpg), with default values
input_layer_variables = {
    'time': 0.2,                # x1
    'cart_value': 0.2,          # x2
    'delivery_fee': 0.9,        # x3
    'distance': 0.9,            # x4
    'payment_dwell_time': 0.9,  # x5
    'back_exit_behavior': 0.9,  # x6
}
INPUT_NAMES = list(input_layer_variables)

# Input -> hidden layer 1 weights (fully connected), columns follow INPUT_NAMES.
# shortcut: placeholder weights, tune or fit them to data.
W1 = np.array([
    [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],  # H1 brand_love
    [0.6, 0.5, 0.4, 0.3, 0.2, 0.1],  # H2 program_love
])

def abort_if_forcing_term_doesnt_exist(forcing_term_id):
    if forcing_term_id not in compute_forcing_terms:
        abort(404, message="Forcing term {} doesn't exist".format(forcing_term_id))

parser = reqparse.RequestParser()
parser.add_argument('forcing_term')

# ForcingTerm
# shows a single forcing term item and lets you delete a forcing term item
class ForcingTerm(Resource):
    def get(self, forcing_term_id):
        abort_if_forcing_term_doesnt_exist(forcing_term_id)
        return compute_forcing_terms[forcing_term_id]

    def delete(self, forcing_term_id):
        abort_if_forcing_term_doesnt_exist(forcing_term_id)
        del compute_forcing_terms[forcing_term_id]
        return '', 204

    def put(self, forcing_term_id):
        args = parser.parse_args()
        forcing_term = {'forcing_term': args['forcing_term']}
        compute_forcing_terms[forcing_term_id] = forcing_term
        return forcing_term, 201

# Input Variable List
# show a list of all input layer variables

class InputLayer(Resource):
    def get(self):
        return input_layer_variables

# ForcingTermList
# shows a list of all forcing terms, and lets you POST to compute forcing term
class ForcingTermList(Resource):
    def get(self):
        return compute_forcing_terms

    def post(self):
        dl_parser = reqparse.RequestParser()
        for name in INPUT_NAMES:
            dl_parser.add_argument(name, type=float, required=True, help=f'{name} must be a float value')
        args = dl_parser.parse_args()

        # Generate a new forcing_term_id
        max_id = 0
        for key in compute_forcing_terms.keys():
            if key.startswith('forcing_term'):
                try:
                    num = int(key.removeprefix('forcing_term'))
                    max_id = max(max_id, num)
                except ValueError:
                    continue
        forcing_term_id = f'forcing_term{max_id + 1}'

        # Model parameters
        dt = 0.01  # Time step
        eta = 0.9
        omega = 0.5
        wH1 = 0.88
        wH2 = 0.87

        array_length = 800  # Fixed number of time steps

        # Input layer x1..x6 (constant over time, taken from the request)
        x = np.array([args[name] for name in INPUT_NAMES])

        # Hidden layer 1 (fully connected): scaled sum of all inputs per node
        brand_love, program_love = W1 @ x / W1.sum(axis=1)

        # Hidden layer 2: both nodes take both hidden-1 nodes
        disappointment = omega * program_love + (1 - omega) * brand_love  # H4
        convenience = wH1 * brand_love + wH2 * program_love               # H5

        # Output Y: cart abandon moves toward the aggregated impact over time
        aggregated = (1 - disappointment) * convenience
        cart_abandon = np.zeros(array_length)
        cart_abandon[0] = 0.1
        for t in range(1, array_length):
            cart_abandon[t] = cart_abandon[t-1] + eta * (aggregated - cart_abandon[t-1]) * dt

        # Store the computed forcing term
        compute_forcing_terms[forcing_term_id] = {'forcing_term': str(cart_abandon[-1])}

        # Return the new forcing term
        return {forcing_term_id: {'forcing_term': float(cart_abandon[-1])}}, 201

##
## Actually setup the Api resource routing here
##
api.add_resource(ForcingTermList, '/forcing_terms')
api.add_resource(InputLayer, '/input_variables')
api.add_resource(ForcingTerm, '/forcing_terms/<forcing_term_id>')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
