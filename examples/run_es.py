import argparse
import os
import pdb
import torch
import torch.backends.cudnn
import tqdm
import torch.nn.functional as F

from torchpack.utils import io
from torchpack.utils.config import configs
from torchpack.utils.logging import logger
from core import builder
from torchquantum.utils import legalize_unitary
from qiskit import IBMQ
from core.tools import EvolutionEngine


def estimate_noise(model, solution):
    return 0


def evaluate_all(model, dataflow, solutions):
    scores = []

    for solution in solutions:
        if configs.qiskit.use_qiskit:
            model.qiskit_processor.set_layout(solution['layout'])
        model.set_sample_arch(solution['arch'])
        with torch.no_grad():
            target_all = None
            output_all = None
            for feed_dict in tqdm.tqdm(dataflow):
                if configs.run.device == 'gpu':
                    inputs = feed_dict['image'].cuda(non_blocking=True)
                    targets = feed_dict['digit'].cuda(non_blocking=True)
                else:
                    inputs = feed_dict['image']
                    targets = feed_dict['digit']
                if configs.qiskit.use_qiskit:
                    outputs = model.forward_qiskit(inputs)
                else:
                    outputs = model.forward(inputs)

                if target_all is None:
                    target_all = targets
                    output_all = outputs
                else:
                    target_all = torch.cat([target_all, targets], dim=0)
                    output_all = torch.cat([output_all, outputs], dim=0)

        k = 1
        _, indices = output_all.topk(k, dim=1)
        masks = indices.eq(target_all.view(-1, 1).expand_as(indices))
        size = target_all.shape[0]
        corrects = masks.sum().item()
        accuracy = corrects / size
        loss = F.nll_loss(output_all, target_all).item()
        logger.info(f"Accuracy: {accuracy}")
        logger.info(f"Loss: {loss}")

        scores.append(loss + estimate_noise(model, solution))

    return scores


def main() -> None:
    torch.backends.cudnn.benchmark = True

    parser = argparse.ArgumentParser()
    parser.add_argument('config', metavar='FILE', help='config file')
    parser.add_argument('--run_dir', metavar='DIR', help='run directory')
    parser.add_argument('--pdb', action='store_true', help='pdb')
    parser.add_argument('--gpu', type=str, help='gpu ids', default=None)
    args, opts = parser.parse_known_args()

    configs.load(os.path.join(args.run_dir, 'metainfo', 'configs.yaml'))
    configs.load(args.config, recursive=True)
    configs.update(opts)

    if configs.debug.pdb or args.pdb:
        pdb.set_trace()

    if args.gpu is not None:
        os.environ['CUDA_VISIBLE_DEVICES'] = args.gpu

    if configs.run.device == 'gpu':
        device = torch.device('cuda')
    elif configs.run.device == 'cpu':
        device = torch.device('cpu')
    else:
        raise ValueError(configs.run.device)

    logger.info(f'Evaluation started: "{args.run_dir}".' + '\n' + f'{configs}')

    if configs.qiskit.use_qiskit:
        IBMQ.load_account()
        if configs.run.bsz == 'qiskit_max':
            configs.run.bsz = IBMQ.get_provider(hub='ibm-q').get_backend(
                configs.qiskit.backend_name).configuration().max_experiments

    dataset = builder.make_dataset()
    sampler = torch.utils.data.SequentialSampler(dataset['test'])
    dataflow = torch.utils.data.DataLoader(
        dataset['test'],
        sampler=sampler,
        batch_size=configs.run.bsz,
        num_workers=configs.run.workers_per_gpu,
        pin_memory=True)

    state_dict = io.load(
        os.path.join(args.run_dir, 'checkpoints', 'max-acc-largest_valid.pt'))
    model = state_dict['model_arch']

    if configs.legalize_unitary:
        legalize_unitary(model)
    model.to(device)
    model.eval()
    model.load_state_dict(state_dict['model'])

    if configs.qiskit.use_qiskit:
        qiskit_processor = builder.make_qiskit_processor()
        model.set_qiskit_processor(qiskit_processor)
        n_available_wires = len(IBMQ.get_provider(hub='ibm-q').get_backend(
            configs.qiskit.backend_name).properties().qubits)
    else:
        n_available_wires = model.q_device.n_wires

    total_params = sum(p.numel() for p in model.parameters())
    logger.info(f'Model Size: {total_params}')

    es_engine = EvolutionEngine(
        population_size=configs.es.population_size,
        parent_size=configs.es.parent_size,
        mutation_size=configs.es.mutation_size,
        mutation_prob=configs.es.mutation_prob,
        crossover_size=configs.es.crossover_size,
        n_wires=model.q_device.n_wires,
        n_available_wires=n_available_wires,
        arch_space=model.arch_space,
    )

    logger.info(f"Start Evolution Search")
    for k in range(configs.es.n_iterations):
        logger.info(f"ES iteration {k}:")
        solutions = es_engine.ask()
        scores = evaluate_all(model, dataflow, solutions)
        es_engine.tell(scores)
        logger.info(f"Best solution: {es_engine.best_solution} \t with score")
        logger.info(f"Best score: {es_engine.best_score}")


if __name__ == '__main__':
    main()
