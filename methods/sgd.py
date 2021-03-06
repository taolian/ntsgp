import argparse
from sklearn import linear_model, preprocessing
from scaffold import *


def make_parser():
    parser = base_parser('Run SGD regression on ers data')
    parser.add_argument(
        '-l', '--loss',
        choices=('squared_loss', 'huber', 'epsilon_insensitive',
                 'squared_epsilon_insensitive'),
        default='squared_loss',
        help='loss function to minimize')
    parser.add_argument(
        '-r', '--alpha',
        type=float, default=0.0001,
        help='regularization constant')
    parser.add_argument(
        '-p', '--penalty',
        choices=('l1', 'l2', 'elasticnet'), default='l1',
        help='type of regularization penalty to use')
    parser.add_argument(
        '-i', '--niter',
        type=int, default=5,
        help='number of iterations to run')
    parser.add_argument(
        '-lr', '--lrate',
        type=float, default=0.01,
        help='learning rate')
    return parser


if __name__ == "__main__":
    args = setup(make_parser)

    # Read data.
    tokeep = \
        ['grdpts', 'sid', 'cid', 'termnum', 'major', 'sterm', 'cohort', 'cs']
    tokeep += RVALS
    data = pd.read_csv(args.data_file, usecols=tokeep).sort(['sid', 'termnum'])

    # Build classifier.
    clf = sklearn_model(
        linear_model.SGDRegressor, loss=args.loss, penalty=args.penalty,
        alpha=args.alpha, n_iter=args.niter, eta0=args.lrate)

    results = method_error(data, clf, True, predict_cold_start=args.cold_start)
    by = args.plot if args.plot else ('cs' if args.cold_start else 'termnum')
    evaluation = eval_results(results, by=by)
    print evaluation

    if args.plot == 'pred':
        g1, g2 = plot_predictions(results)
    elif args.plot in ['termnum', 'sterm', 'cohort']:
        ax1, ax2 = plot_error_by(args.plot, results)
