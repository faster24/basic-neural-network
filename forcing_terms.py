"""Original REST API for scoring inputs by hand. Kept in memory, as before."""
from flask_restful import reqparse, abort, Resource

from model import INPUT_NAMES, DEFAULT_INPUTS, compute_cart_abandon

compute_forcing_terms = {
    'forcing_term1': {'forcing_term': '0.9'},
    'forcing_term2': {'forcing_term': '0.1'},
    'forcing_term3': {'forcing_term': '0.5'},
}


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
        return DEFAULT_INPUTS


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

        value = compute_cart_abandon([args[name] for name in INPUT_NAMES])
        compute_forcing_terms[forcing_term_id] = {'forcing_term': str(value)}
        return {forcing_term_id: {'forcing_term': value}}, 201


def register(api):
    api.add_resource(ForcingTermList, '/forcing_terms')
    api.add_resource(InputLayer, '/input_variables')
    api.add_resource(ForcingTerm, '/forcing_terms/<forcing_term_id>')
